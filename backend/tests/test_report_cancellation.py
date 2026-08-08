from app.services.report_agent import Report, ReportManager, ReportStatus


def test_cancel_report_persists_terminal_failed_state(tmp_path, monkeypatch):
    monkeypatch.setattr(ReportManager, "REPORTS_DIR", str(tmp_path))
    report = Report(
        report_id="report_cancel",
        simulation_id="sim_1",
        graph_id="graph_1",
        simulation_requirement="test",
        status=ReportStatus.PLANNING,
    )
    ReportManager.save_report(report)

    cancelled = ReportManager.cancel_report(report.report_id)

    assert cancelled is not None
    assert cancelled.status == ReportStatus.FAILED
    assert ReportManager.is_cancel_requested(report.report_id)
    persisted = ReportManager.get_report(report.report_id)
    assert persisted.status == ReportStatus.FAILED
    assert persisted.error == "Report generation cancelled by user"
