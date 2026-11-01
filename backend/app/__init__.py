"""
MiroFish Backend - Flask application factory
"""

import os
import warnings

# Suppress multiprocessing resource_tracker warnings (from third-party libs such as transformers)
# Must be set before all other imports
warnings.filterwarnings("ignore", message=".*resource_tracker.*")

from flask import Flask, request
from flask_cors import CORS

from .config import Config
from .utils.locale import t
from .utils.logger import setup_logger, get_logger, redact_han_text


def create_app(config_class=Config):
    """Flask application factory function"""
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # JSON encoding: show non-ASCII text as-is (instead of \uXXXX escapes)
    # Flask >= 2.3 uses app.json.ensure_ascii; older versions use the JSON_AS_ASCII config
    if hasattr(app, 'json') and hasattr(app.json, 'ensure_ascii'):
        app.json.ensure_ascii = False
    
    # Set up logging
    logger = setup_logger('mirofish')
    
    # Only print startup info in the reloader child process (avoid printing twice in debug mode)
    is_reloader_process = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
    debug_mode = app.config.get('DEBUG', False)
    should_log_startup = not debug_mode or is_reloader_process
    
    if should_log_startup:
        logger.info("=" * 50)
        logger.info(t("console.backendStarting"))
        logger.info("=" * 50)
    
    # Enable CORS
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    
    # Register simulation process cleanup (terminate all simulations when the server shuts down)
    from .services.simulation_runner import SimulationRunner
    SimulationRunner.register_cleanup()
    if should_log_startup:
        logger.info(t("console.simulationCleanupRegistered"))
    
    # Request logging middleware
    @app.before_request
    def log_request():
        logger = get_logger('mirofish.request')
        logger.debug(t("console.httpRequest", method=request.method, path=request.path))
        if request.content_type and 'json' in request.content_type:
            logger.debug(t("console.httpRequestBody", body=request.get_json(silent=True)))
    
    @app.after_request
    def log_response(response):
        logger = get_logger('mirofish.request')
        logger.debug(t("console.httpResponse", status=response.status_code))
        if response.is_json:
            payload = response.get_json(silent=True)

            def sanitize(value, key=None):
                if isinstance(value, dict):
                    return {k: sanitize(v, k) for k, v in value.items()}
                if isinstance(value, list):
                    return [sanitize(v, key) for v in value]
                if key in {"error", "message", "traceback"} and isinstance(value, str):
                    return redact_han_text(value)
                return value

            if payload is not None:
                response.set_data(app.json.dumps(sanitize(payload)))
        return response
    
    # Register blueprints
    from .api import graph_bp, simulation_bp, report_bp
    app.register_blueprint(graph_bp, url_prefix='/api/graph')
    app.register_blueprint(simulation_bp, url_prefix='/api/simulation')
    app.register_blueprint(report_bp, url_prefix='/api/report')
    
    # Health check
    @app.route('/health')
    def health():
        return {'status': 'ok', 'service': 'MiroFish Backend'}
    
    if should_log_startup:
        logger.info(t("console.backendStarted"))
    
    return app
