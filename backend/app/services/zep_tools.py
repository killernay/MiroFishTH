"""
Zep retrieval tools service
Wraps graph search, node reading, edge queries, etc. for use by the Report Agent

Core retrieval tools (optimized):
1. InsightForge (deep insight retrieval) - the most powerful hybrid retrieval; auto-generates sub-questions and retrieves across multiple dimensions
2. PanoramaSearch (breadth search) - get the full picture, including expired content
3. QuickSearch (simple search) - fast retrieval
"""

import re
import time
import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from zep_cloud import NotFoundError

from ..config import Config
from ..utils.logger import get_logger
from ..utils.llm_client import LLMClient
from ..utils.locale import get_language_instruction, get_locale, t
from ..utils.zep_paging import fetch_all_nodes, fetch_all_edges
from ..utils.zep import (
    call_zep_read_with_retry,
    get_zep_client,
    normalize_zep_search_limit,
    normalize_zep_search_query,
)

logger = get_logger('mirofish.zep_tools')


@dataclass
class SearchResult:
    """Search result"""
    facts: List[str]
    edges: List[Dict[str, Any]]
    nodes: List[Dict[str, Any]]
    query: str
    total_count: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "facts": self.facts,
            "edges": self.edges,
            "nodes": self.nodes,
            "query": self.query,
            "total_count": self.total_count
        }
    
    def to_text(self) -> str:
        """Convert to text format for LLM consumption"""
        text_parts = [
            t('zepTools.searchQuery', query=self.query),
            t('zepTools.relatedInformationCount', count=self.total_count),
        ]
        
        if self.facts:
            text_parts.append(f"\n### {t('zepTools.relatedSourceFacts')}")
            for i, fact in enumerate(self.facts, 1):
                text_parts.append(f"{i}. {fact}")
        
        return "\n".join(text_parts)


@dataclass
class NodeInfo:
    """Node information"""
    uuid: str
    name: str
    labels: List[str]
    summary: str
    attributes: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "labels": self.labels,
            "summary": self.summary,
            "attributes": self.attributes
        }
    
    def to_text(self) -> str:
        """Convert to text format"""
        entity_type = next((l for l in self.labels if l not in ["Entity", "Node"]), t('zepTools.unknownType'))
        return t('zepTools.nodeText', name=self.name, entityType=entity_type, summary=self.summary)


@dataclass
class EdgeInfo:
    """Edge information"""
    uuid: str
    name: str
    fact: str
    source_node_uuid: str
    target_node_uuid: str
    source_node_name: Optional[str] = None
    target_node_name: Optional[str] = None
    # Temporal information
    created_at: Optional[str] = None
    valid_at: Optional[str] = None
    invalid_at: Optional[str] = None
    expired_at: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "fact": self.fact,
            "source_node_uuid": self.source_node_uuid,
            "target_node_uuid": self.target_node_uuid,
            "source_node_name": self.source_node_name,
            "target_node_name": self.target_node_name,
            "created_at": self.created_at,
            "valid_at": self.valid_at,
            "invalid_at": self.invalid_at,
            "expired_at": self.expired_at
        }
    
    def to_text(self, include_temporal: bool = False) -> str:
        """Convert to text format"""
        source = self.source_node_name or self.source_node_uuid[:8]
        target = self.target_node_name or self.target_node_uuid[:8]
        base_text = t('zepTools.edgeText', source=source, relation=self.name, target=target, fact=self.fact)
        
        if include_temporal:
            valid_at = self.valid_at or t('zepTools.unknown')
            invalid_at = self.invalid_at or t('zepTools.present')
            base_text += "\n" + t('zepTools.validity', start=valid_at, end=invalid_at)
            if self.expired_at:
                base_text += " " + t('zepTools.expiredAt', value=self.expired_at)
        
        return base_text
    
    @property
    def is_expired(self) -> bool:
        """Whether expired"""
        return self.expired_at is not None
    
    @property
    def is_invalid(self) -> bool:
        """Whether invalidated"""
        return self.invalid_at is not None


@dataclass
class InsightForgeResult:
    """
    Deep insight retrieval result (InsightForge)
    Contains retrieval results for multiple sub-questions, plus synthesized analysis
    """
    query: str
    simulation_requirement: str
    sub_queries: List[str]
    
    # Retrieval results per dimension
    semantic_facts: List[str] = field(default_factory=list)  # Semantic search results
    entity_insights: List[Dict[str, Any]] = field(default_factory=list)  # Entity insights
    relationship_chains: List[str] = field(default_factory=list)  # Relationship chains
    
    # Statistics
    total_facts: int = 0
    total_entities: int = 0
    total_relationships: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "simulation_requirement": self.simulation_requirement,
            "sub_queries": self.sub_queries,
            "semantic_facts": self.semantic_facts,
            "entity_insights": self.entity_insights,
            "relationship_chains": self.relationship_chains,
            "total_facts": self.total_facts,
            "total_entities": self.total_entities,
            "total_relationships": self.total_relationships
        }
    
    def to_text(self) -> str:
        """Convert to detailed text format for LLM consumption"""
        text_parts = [
            f"## {t('zepTools.insightTitle')}",
            t('zepTools.analysisQuestion', query=self.query),
            t('zepTools.simulationScenario', scenario=self.simulation_requirement),
            f"\n### {t('zepTools.predictionStats')}",
            t('zepTools.relatedFacts', count=self.total_facts),
            t('zepTools.entitiesCount', count=self.total_entities),
            t('zepTools.relationshipsCount', count=self.total_relationships),
        ]
        
        # Sub-questions
        if self.sub_queries:
            text_parts.append(f"\n### {t('zepTools.subQuestions')}")
            for i, sq in enumerate(self.sub_queries, 1):
                text_parts.append(f"{i}. {sq}")
        
        # Semantic search results
        if self.semantic_facts:
            text_parts.append(f"\n### {t('zepTools.keySourceFacts')}")
            for i, fact in enumerate(self.semantic_facts, 1):
                text_parts.append(f"{i}. \"{fact}\"")
        
        # Entity insights
        if self.entity_insights:
            text_parts.append(f"\n### {t('zepTools.coreEntities')}")
            for entity in self.entity_insights:
                text_parts.append(f"- **{entity.get('name', t('zepTools.unknown'))}** ({entity.get('type', t('zepTools.entity'))})")
                if entity.get('summary'):
                    text_parts.append(t('zepTools.summary', value=entity.get('summary')))
                if entity.get('related_facts'):
                    text_parts.append(t('zepTools.relatedFacts', count=len(entity.get('related_facts', []))))
        
        # Relationship chains
        if self.relationship_chains:
            text_parts.append(f"\n### {t('zepTools.relationshipChains')}")
            for chain in self.relationship_chains:
                text_parts.append(f"- {chain}")
        
        return "\n".join(text_parts)


@dataclass
class PanoramaResult:
    """
    Breadth search result (Panorama)
    Contains all relevant information, including expired content
    """
    query: str
    
    # All nodes
    all_nodes: List[NodeInfo] = field(default_factory=list)
    # All edges (including expired ones)
    all_edges: List[EdgeInfo] = field(default_factory=list)
    # Currently valid facts
    active_facts: List[str] = field(default_factory=list)
    # Expired/invalidated facts (history)
    historical_facts: List[str] = field(default_factory=list)
    
    # Statistics
    total_nodes: int = 0
    total_edges: int = 0
    active_count: int = 0
    historical_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "all_nodes": [n.to_dict() for n in self.all_nodes],
            "all_edges": [e.to_dict() for e in self.all_edges],
            "active_facts": self.active_facts,
            "historical_facts": self.historical_facts,
            "total_nodes": self.total_nodes,
            "total_edges": self.total_edges,
            "active_count": self.active_count,
            "historical_count": self.historical_count
        }
    
    def to_text(self) -> str:
        """Convert to text format (full version, no truncation)"""
        text_parts = [
            f"## {t('zepTools.panoramaTitle')}",
            t('zepTools.query', query=self.query),
            f"\n### {t('zepTools.stats')}",
            t('zepTools.totalNodes', count=self.total_nodes),
            t('zepTools.totalEdges', count=self.total_edges),
            t('zepTools.activeFactsCount', count=self.active_count),
            t('zepTools.historicalFactsCount', count=self.historical_count),
        ]
        
        # Currently valid facts (full output, no truncation)
        if self.active_facts:
            text_parts.append(f"\n### {t('zepTools.activeSourceFacts')}")
            for i, fact in enumerate(self.active_facts, 1):
                text_parts.append(f"{i}. \"{fact}\"")
        
        # Historical/expired facts (full output, no truncation)
        if self.historical_facts:
            text_parts.append(f"\n### {t('zepTools.historicalSourceFacts')}")
            for i, fact in enumerate(self.historical_facts, 1):
                text_parts.append(f"{i}. \"{fact}\"")
        
        # Key entities (full output, no truncation)
        if self.all_nodes:
            text_parts.append(f"\n### {t('zepTools.entities')}")
            for node in self.all_nodes:
                entity_type = next((l for l in node.labels if l not in ["Entity", "Node"]), t('zepTools.entity'))
                text_parts.append(f"- **{node.name}** ({entity_type})")
        
        return "\n".join(text_parts)


@dataclass
class AgentInterview:
    """Interview result for a single Agent"""
    agent_name: str
    agent_role: str  # Role type (e.g. student, teacher, media)
    agent_bio: str  # Bio
    question: str  # Interview question
    response: str  # Interview answer
    key_quotes: List[str] = field(default_factory=list)  # Key quotes
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "agent_role": self.agent_role,
            "agent_bio": self.agent_bio,
            "question": self.question,
            "response": self.response,
            "key_quotes": self.key_quotes
        }
    
    def to_text(self) -> str:
        text = f"**{self.agent_name}** ({self.agent_role})\n"
        # Show full agent_bio, no truncation
        text += f"_{t('zepTools.bio', value=self.agent_bio)}_\n\n"
        text += f"**Q:** {self.question}\n\n"
        text += f"**A:** {self.response}\n"
        if self.key_quotes:
            text += f"\n**{t('zepTools.keyQuotes')}:**\n"
            for quote in self.key_quotes:
                # Clean up various quote marks
                clean_quote = quote.replace('\u201c', '').replace('\u201d', '').replace('"', '')
                clean_quote = clean_quote.replace('\u300c', '').replace('\u300d', '')
                clean_quote = clean_quote.strip()
                # Strip leading punctuation
                while clean_quote and clean_quote[0] in '，,；;：:、。！？\n\r\t ':
                    clean_quote = clean_quote[1:]
                # Skip junk content carrying question-number labels ("Question 1:" / "คำถาม 1:")
                skip = bool(re.search(r'(?:Question|คำถาม)\s*[1-9]\s*[：:]', clean_quote, flags=re.IGNORECASE))
                if skip:
                    continue
                # Truncate overly long content (at sentence end, not hard cut)
                if len(clean_quote) > 150:
                    dot_pos = clean_quote.find('\u3002', 80)
                    if dot_pos > 0:
                        clean_quote = clean_quote[:dot_pos + 1]
                    else:
                        clean_quote = clean_quote[:147] + "..."
                if clean_quote and len(clean_quote) >= 10:
                    text += f'> "{clean_quote}"\n'
        return text


@dataclass
class InterviewResult:
    """
    Interview result (Interview)
    Contains interview answers from multiple simulated Agents
    """
    interview_topic: str  # Interview topic
    interview_questions: List[str]  # List of interview questions
    
    # Agents selected for interview
    selected_agents: List[Dict[str, Any]] = field(default_factory=list)
    # Interview answers from each Agent
    interviews: List[AgentInterview] = field(default_factory=list)
    
    # Reasoning for Agent selection
    selection_reasoning: str = ""
    # Consolidated interview summary
    summary: str = ""
    
    # Statistics
    total_agents: int = 0
    interviewed_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "interview_topic": self.interview_topic,
            "interview_questions": self.interview_questions,
            "selected_agents": self.selected_agents,
            "interviews": [i.to_dict() for i in self.interviews],
            "selection_reasoning": self.selection_reasoning,
            "summary": self.summary,
            "total_agents": self.total_agents,
            "interviewed_count": self.interviewed_count
        }
    
    def to_text(self) -> str:
        """Convert to detailed text format for LLM consumption and report citation"""
        text_parts = [
            f"## {t('zepTools.interviewTitle')}",
            t('zepTools.interviewTopic', topic=self.interview_topic),
            t('zepTools.interviewCount', completed=self.interviewed_count, total=self.total_agents),
            f"\n### {t('zepTools.selectionReasoning')}",
            self.selection_reasoning or t('zepTools.autoSelected'),
            "\n---",
            f"\n### {t('zepTools.interviewRecords')}",
        ]

        if self.interviews:
            for i, interview in enumerate(self.interviews, 1):
                text_parts.append(t('zepTools.interviewNumber', number=i, name=interview.agent_name))
                text_parts.append(interview.to_text())
                text_parts.append("\n---")
        else:
            text_parts.append(f"{t('zepTools.noInterviewRecords')}\n\n---")

        text_parts.append(f"\n### {t('zepTools.interviewSummary')}")
        text_parts.append(self.summary or t('zepTools.noSummary'))

        return "\n".join(text_parts)


class ZepToolsService:
    """
    Zep retrieval tools service
    
    [Core retrieval tools - optimized]
    1. insight_forge - deep insight retrieval (most powerful; auto-generates sub-questions, multi-dimensional retrieval)
    2. panorama_search - breadth search (full picture, including expired content)
    3. quick_search - simple search (fast retrieval)
    4. interview_agents - deep interview (interview simulated Agents for multiple perspectives)
    
    [Basic tools]
    - search_graph - graph semantic search
    - get_all_nodes - get all nodes of the graph
    - get_all_edges - get all edges of the graph (with temporal info)
    - get_node_detail - get node details
    - get_node_edges - get edges related to a node
    - get_entities_by_type - get entities by type
    - get_entity_summary - get an entity's relationship summary
    """
    
    # Retry configuration
    MAX_RETRIES = 3
    RETRY_DELAY = 2.0
    
    def __init__(self, api_key: Optional[str] = None, llm_client: Optional[LLMClient] = None):
        self.api_key = api_key or Config.ZEP_API_KEY
        if not self.api_key:
            raise ValueError(t("console.zepApiKeyMissing"))
        
        self.client = get_zep_client(self.api_key)
        # LLM client used by InsightForge to generate sub-questions
        self._llm_client = llm_client
        logger.info(t("console.zepToolsInitialized"))
    
    @property
    def llm(self) -> LLMClient:
        """Lazily initialize the LLM client"""
        if self._llm_client is None:
            self._llm_client = LLMClient()
        return self._llm_client
    
    def _call_with_retry(self, func, operation_name: str, max_retries: int = None):
        """Retry one safe read using typed Zep/HTTPX error classification."""

        return call_zep_read_with_retry(
            func,
            operation_name=operation_name,
            max_attempts=max_retries or self.MAX_RETRIES,
            initial_delay=self.RETRY_DELAY,
        )
    
    def search_graph(
        self, 
        graph_id: str, 
        query: str, 
        limit: int = 10,
        scope: str = "edges"
    ) -> SearchResult:
        """
        Graph semantic search
        
        Uses hybrid search (semantic + BM25) to find relevant info in the graph.
        Falls back to local keyword matching if the Zep Cloud search API is unavailable.
        
        Args:
            graph_id: Graph ID (Standalone Graph)
            query: Search query
            limit: Number of results to return
            scope: Search scope, "edges" or "nodes"
            
        Returns:
            SearchResult: Search result
        """
        logger.info(t("console.graphSearch", graphId=graph_id, query=query[:50]))
        
        zep_query = normalize_zep_search_query(query)
        zep_limit = normalize_zep_search_limit(limit)

        try:
            search_results = self._call_with_retry(
                func=lambda: self.client.graph.search(
                    graph_id=graph_id,
                    query=zep_query,
                    limit=zep_limit,
                    scope=scope,
                    reranker="cross_encoder"
                ),
                operation_name=t("console.graphSearchOp", graphId=graph_id)
            )
            
            facts = []
            edges = []
            nodes = []
            
            # Parse edge search results
            if hasattr(search_results, 'edges') and search_results.edges:
                for edge in search_results.edges:
                    if hasattr(edge, 'fact') and edge.fact:
                        facts.append(edge.fact)
                    edges.append({
                        "uuid": getattr(edge, 'uuid_', None) or getattr(edge, 'uuid', ''),
                        "name": getattr(edge, 'name', ''),
                        "fact": getattr(edge, 'fact', ''),
                        "source_node_uuid": getattr(edge, 'source_node_uuid', ''),
                        "target_node_uuid": getattr(edge, 'target_node_uuid', ''),
                    })
            
            # Parse node search results
            if hasattr(search_results, 'nodes') and search_results.nodes:
                for node in search_results.nodes:
                    nodes.append({
                        "uuid": getattr(node, 'uuid_', None) or getattr(node, 'uuid', ''),
                        "name": getattr(node, 'name', ''),
                        "labels": getattr(node, 'labels', []),
                        "summary": getattr(node, 'summary', ''),
                    })
                    # Node summary also counts as a fact
                    if hasattr(node, 'summary') and node.summary:
                        facts.append(f"[{node.name}]: {node.summary}")
            
            logger.info(t("console.searchComplete", count=len(facts)))
            
            return SearchResult(
                facts=facts,
                edges=edges,
                nodes=nodes,
                query=query,
                total_count=len(facts)
            )
            
        except Exception as e:
            # Authentication, invalid input, missing graphs, and exhausted
            # transient failures must remain visible to the report workflow.
            logger.error(t("console.zepSearchApiFallback", error=str(e)))
            raise
    
    def _local_search(
        self, 
        graph_id: str, 
        query: str, 
        limit: int = 10,
        scope: str = "edges"
    ) -> SearchResult:
        """
        Local keyword-matching search (fallback for the Zep Search API)
        
        Fetch all edges/nodes, then perform keyword matching locally
        
        Args:
            graph_id: Graph ID
            query: Search query
            limit: Number of results to return
            scope: Search scope
            
        Returns:
            SearchResult: Search result
        """
        logger.info(t("console.usingLocalSearch", query=query[:30]))
        
        facts = []
        edges_result = []
        nodes_result = []
        
        # Extract query keywords (simple tokenization)
        query_lower = query.lower()
        keywords = [w.strip() for w in query_lower.replace(',', ' ').replace('，', ' ').split() if len(w.strip()) > 1]
        
        def match_score(text: str) -> int:
            """Compute match score between text and query"""
            if not text:
                return 0
            text_lower = text.lower()
            # Exact query match
            if query_lower in text_lower:
                return 100
            # Keyword match
            score = 0
            for keyword in keywords:
                if keyword in text_lower:
                    score += 10
            return score
        
        try:
            if scope in ["edges", "both"]:
                # Fetch all edges and match
                all_edges = self.get_all_edges(graph_id)
                scored_edges = []
                for edge in all_edges:
                    score = match_score(edge.fact) + match_score(edge.name)
                    if score > 0:
                        scored_edges.append((score, edge))
                
                # Sort by score
                scored_edges.sort(key=lambda x: x[0], reverse=True)
                
                for score, edge in scored_edges[:limit]:
                    if edge.fact:
                        facts.append(edge.fact)
                    edges_result.append({
                        "uuid": edge.uuid,
                        "name": edge.name,
                        "fact": edge.fact,
                        "source_node_uuid": edge.source_node_uuid,
                        "target_node_uuid": edge.target_node_uuid,
                    })
            
            if scope in ["nodes", "both"]:
                # Fetch all nodes and match
                all_nodes = self.get_all_nodes(graph_id)
                scored_nodes = []
                for node in all_nodes:
                    score = match_score(node.name) + match_score(node.summary)
                    if score > 0:
                        scored_nodes.append((score, node))
                
                scored_nodes.sort(key=lambda x: x[0], reverse=True)
                
                for score, node in scored_nodes[:limit]:
                    nodes_result.append({
                        "uuid": node.uuid,
                        "name": node.name,
                        "labels": node.labels,
                        "summary": node.summary,
                    })
                    if node.summary:
                        facts.append(f"[{node.name}]: {node.summary}")
            
            logger.info(t("console.localSearchComplete", count=len(facts)))
            
        except Exception as e:
            logger.error(t("console.localSearchFailed", error=str(e)))
        
        return SearchResult(
            facts=facts,
            edges=edges_result,
            nodes=nodes_result,
            query=query,
            total_count=len(facts)
        )
    
    def get_all_nodes(self, graph_id: str) -> List[NodeInfo]:
        """
        Get all nodes of the graph (paginated)

        Args:
            graph_id: Graph ID

        Returns:
            List of nodes
        """
        logger.info(t("console.fetchingAllNodes", graphId=graph_id))

        nodes = fetch_all_nodes(self.client, graph_id)

        result = []
        for node in nodes:
            node_uuid = getattr(node, 'uuid_', None) or getattr(node, 'uuid', None) or ""
            result.append(NodeInfo(
                uuid=str(node_uuid) if node_uuid else "",
                name=node.name or "",
                labels=node.labels or [],
                summary=node.summary or "",
                attributes=node.attributes or {}
            ))

        logger.info(t("console.fetchedNodes", count=len(result)))
        return result

    def get_all_edges(self, graph_id: str, include_temporal: bool = True) -> List[EdgeInfo]:
        """
        Get all edges of the graph (paginated, with temporal info)

        Args:
            graph_id: Graph ID
            include_temporal: Whether to include temporal info (default True)

        Returns:
            List of edges (with created_at, valid_at, invalid_at, expired_at)
        """
        logger.info(t("console.fetchingAllEdges", graphId=graph_id))

        edges = fetch_all_edges(self.client, graph_id)

        result = []
        for edge in edges:
            edge_uuid = getattr(edge, 'uuid_', None) or getattr(edge, 'uuid', None) or ""
            edge_info = EdgeInfo(
                uuid=str(edge_uuid) if edge_uuid else "",
                name=edge.name or "",
                fact=edge.fact or "",
                source_node_uuid=edge.source_node_uuid or "",
                target_node_uuid=edge.target_node_uuid or ""
            )

            # Add temporal info
            if include_temporal:
                edge_info.created_at = getattr(edge, 'created_at', None)
                edge_info.valid_at = getattr(edge, 'valid_at', None)
                edge_info.invalid_at = getattr(edge, 'invalid_at', None)
                edge_info.expired_at = getattr(edge, 'expired_at', None)

            result.append(edge_info)

        logger.info(t("console.fetchedEdges", count=len(result)))
        return result
    
    def get_node_detail(self, node_uuid: str) -> Optional[NodeInfo]:
        """
        Get details of a single node
        
        Args:
            node_uuid: Node UUID
            
        Returns:
            Node info or None
        """
        logger.info(t("console.fetchingNodeDetail", uuid=node_uuid[:8]))
        
        try:
            node = self._call_with_retry(
                func=lambda: self.client.graph.node.get(uuid_=node_uuid),
                operation_name=t("console.fetchNodeDetailOp", uuid=node_uuid[:8])
            )
            
            if not node:
                return None
            
            return NodeInfo(
                uuid=getattr(node, 'uuid_', None) or getattr(node, 'uuid', ''),
                name=node.name or "",
                labels=node.labels or [],
                summary=node.summary or "",
                attributes=node.attributes or {}
            )
        except NotFoundError:
            return None
        except Exception as e:
            logger.error(t("console.fetchNodeDetailFailed", error=str(e)))
            raise
    
    def get_node_edges(self, graph_id: str, node_uuid: str) -> List[EdgeInfo]:
        """
        Get all edges related to a node
        
        Fetches all graph edges, then filters those related to the given node
        
        Args:
            graph_id: Graph ID
            node_uuid: Node UUID
            
        Returns:
            List of edges
        """
        logger.info(t("console.fetchingNodeEdges", uuid=node_uuid[:8]))
        
        try:
            # Fetch all graph edges, then filter
            all_edges = self.get_all_edges(graph_id)
            
            result = []
            for edge in all_edges:
                # Check whether the edge relates to the node (as source or target)
                if edge.source_node_uuid == node_uuid or edge.target_node_uuid == node_uuid:
                    result.append(edge)
            
            logger.info(t("console.foundNodeEdges", count=len(result)))
            return result
            
        except Exception as e:
            logger.error(t("console.fetchNodeEdgesFailed", error=str(e)))
            raise
    
    def get_entities_by_type(
        self, 
        graph_id: str, 
        entity_type: str
    ) -> List[NodeInfo]:
        """
        Get entities by type
        
        Args:
            graph_id: Graph ID
            entity_type: Entity type (e.g. Student, PublicFigure)
            
        Returns:
            List of entities matching the type
        """
        logger.info(t("console.fetchingEntitiesByType", type=entity_type))
        
        all_nodes = self.get_all_nodes(graph_id)
        
        filtered = []
        for node in all_nodes:
            # Check whether labels contain the given type
            if entity_type in node.labels:
                filtered.append(node)
        
        logger.info(t("console.foundEntitiesByType", count=len(filtered), type=entity_type))
        return filtered
    
    def get_entity_summary(
        self, 
        graph_id: str, 
        entity_name: str
    ) -> Dict[str, Any]:
        """
        Get the relationship summary of a given entity
        
        Search all info related to the entity and generate a summary
        
        Args:
            graph_id: Graph ID
            entity_name: Entity name
            
        Returns:
            Entity summary info
        """
        logger.info(t("console.fetchingEntitySummary", name=entity_name))
        
        # First search info related to the entity
        search_result = self.search_graph(
            graph_id=graph_id,
            query=entity_name,
            limit=20
        )
        
        # Try to find the entity among all nodes
        all_nodes = self.get_all_nodes(graph_id)
        entity_node = None
        for node in all_nodes:
            if node.name.lower() == entity_name.lower():
                entity_node = node
                break
        
        related_edges = []
        if entity_node:
            # Pass graph_id parameter
            related_edges = self.get_node_edges(graph_id, entity_node.uuid)
        
        return {
            "entity_name": entity_name,
            "entity_info": entity_node.to_dict() if entity_node else None,
            "related_facts": search_result.facts,
            "related_edges": [e.to_dict() for e in related_edges],
            "total_relations": len(related_edges)
        }
    
    def get_graph_statistics(self, graph_id: str) -> Dict[str, Any]:
        """
        Get graph statistics
        
        Args:
            graph_id: Graph ID
            
        Returns:
            Statistics
        """
        logger.info(t("console.fetchingGraphStats", graphId=graph_id))
        
        nodes = self.get_all_nodes(graph_id)
        edges = self.get_all_edges(graph_id)
        
        # Count entity type distribution
        entity_types = {}
        for node in nodes:
            for label in node.labels:
                if label not in ["Entity", "Node"]:
                    entity_types[label] = entity_types.get(label, 0) + 1
        
        # Count relation type distribution
        relation_types = {}
        for edge in edges:
            relation_types[edge.name] = relation_types.get(edge.name, 0) + 1
        
        return {
            "graph_id": graph_id,
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "entity_types": entity_types,
            "relation_types": relation_types
        }
    
    def get_simulation_context(
        self, 
        graph_id: str,
        simulation_requirement: str,
        limit: int = 30
    ) -> Dict[str, Any]:
        """
        Get simulation-related context info
        
        Comprehensively search all info related to the simulation requirement
        
        Args:
            graph_id: Graph ID
            simulation_requirement: Simulation requirement description
            limit: Count limit per info category
            
        Returns:
            Simulation context info
        """
        logger.info(t("console.fetchingSimContext", requirement=simulation_requirement[:50]))
        
        # Search info related to the simulation requirement
        search_result = self.search_graph(
            graph_id=graph_id,
            query=simulation_requirement,
            limit=limit
        )
        
        # Do not enumerate the complete graph during report planning. On Zep's
        # Free plan this turns one planning search into many paginated reads
        # and can delay the report for tens of minutes. The semantic result is
        # the evidence the outline needs; detailed graph inspection remains an
        # explicit tool operation later in the report flow.
        entities = [
            {
                "name": node.get("name", ""),
                "type": (node.get("labels") or ["Entity"])[0],
                "summary": node.get("summary", ""),
            }
            for node in search_result.nodes[:limit]
        ]
        
        return {
            "simulation_requirement": simulation_requirement,
            "related_facts": search_result.facts,
            "graph_statistics": {
                "source": "semantic_search",
                "total_nodes": None,
                "total_edges": None,
            },
            "entities": entities,
            "total_entities": len(entities)
        }
    
    # ========== Core retrieval tools (optimized) ==========
    
    def insight_forge(
        self,
        graph_id: str,
        query: str,
        simulation_requirement: str,
        report_context: str = "",
        max_sub_queries: int = 3
    ) -> InsightForgeResult:
        """
        [InsightForge - deep insight retrieval]
        
        Most powerful hybrid retrieval function; auto-decomposes the question and retrieves across dimensions:
        1. Use LLM to decompose the question into sub-questions
        2. Run semantic search for each sub-question
        3. Extract related entities and fetch their details
        4. Trace relationship chains
        5. Consolidate all results into deep insights
        
        Args:
            graph_id: Graph ID
            query: User question
            simulation_requirement: Simulation requirement description
            report_context: Report context (optional, for more precise sub-question generation)
            max_sub_queries: Maximum number of sub-questions
            
        Returns:
            InsightForgeResult: Deep insight retrieval result
        """
        logger.info(t("console.insightForgeStart", query=query[:50]))
        
        result = InsightForgeResult(
            query=query,
            simulation_requirement=simulation_requirement,
            sub_queries=[]
        )
        
        # Step 1: Use LLM to generate sub-questions
        sub_queries = self._generate_sub_queries(
            query=query,
            simulation_requirement=simulation_requirement,
            report_context=report_context,
            max_queries=max_sub_queries
        )
        result.sub_queries = sub_queries
        logger.info(t("console.generatedSubQueries", count=len(sub_queries)))
        
        # Step 2: Run semantic search for each sub-question
        all_facts = []
        all_edges = []
        seen_facts = set()
        
        for sub_query in sub_queries:
            search_result = self.search_graph(
                graph_id=graph_id,
                query=sub_query,
                limit=15,
                scope="edges"
            )
            
            for fact in search_result.facts:
                if fact not in seen_facts:
                    all_facts.append(fact)
                    seen_facts.add(fact)
            
            all_edges.extend(search_result.edges)
        
        # Also search the original question
        main_search = self.search_graph(
            graph_id=graph_id,
            query=query,
            limit=20,
            scope="edges"
        )
        for fact in main_search.facts:
            if fact not in seen_facts:
                all_facts.append(fact)
                seen_facts.add(fact)
        
        result.semantic_facts = all_facts
        result.total_facts = len(all_facts)
        
        # Step 3: Extract related entity UUIDs from edges.
        # Do not fan out into one graph read per entity here: on Zep Free this
        # turns a bounded report search into dozens of requests and triggers
        # the five-requests-per-minute limit.  The ranked edge facts above are
        # already the evidence used by the report.
        entity_uuids = set()
        for edge_data in all_edges:
            if isinstance(edge_data, dict):
                source_uuid = edge_data.get('source_node_uuid', '')
                target_uuid = edge_data.get('target_node_uuid', '')
                if source_uuid:
                    entity_uuids.add(source_uuid)
                if target_uuid:
                    entity_uuids.add(target_uuid)
        
        entity_insights = []
        node_map = {}
        
        result.entity_insights = entity_insights
        result.total_entities = len(entity_insights)
        
        # Step 4: Build all relationship chains (no count limit)
        relationship_chains = []
        for edge_data in all_edges:  # Process all edges, no truncation
            if isinstance(edge_data, dict):
                source_uuid = edge_data.get('source_node_uuid', '')
                target_uuid = edge_data.get('target_node_uuid', '')
                relation_name = edge_data.get('name', '')
                
                source_name = node_map.get(source_uuid, NodeInfo('', '', [], '', {})).name or source_uuid[:8]
                target_name = node_map.get(target_uuid, NodeInfo('', '', [], '', {})).name or target_uuid[:8]
                
                chain = f"{source_name} --[{relation_name}]--> {target_name}"
                if chain not in relationship_chains:
                    relationship_chains.append(chain)
        
        result.relationship_chains = relationship_chains
        result.total_relationships = len(relationship_chains)
        
        logger.info(t("console.insightForgeComplete", facts=result.total_facts, entities=result.total_entities, relationships=result.total_relationships))
        return result
    
    def _generate_sub_queries(
        self,
        query: str,
        simulation_requirement: str,
        report_context: str = "",
        max_queries: int = 5
    ) -> List[str]:
        """
        Use LLM to generate sub-questions
        
        Decompose a complex question into sub-questions that can be retrieved independently
        """
        system_prompt = f"""You are a question-analysis specialist. Break a complex question into independent sub-questions that can be observed in a simulation.

Requirements:
1. Each sub-question must be specific enough to find relevant agent actions or events.
2. Cover different dimensions such as who, what, why, how, when, and where.
3. Keep every sub-question relevant to the simulation scenario.
4. Return JSON only: {{"sub_queries": ["sub-question 1", "sub-question 2"]}}.

{get_language_instruction()}"""

        user_prompt = f"""Simulation requirement:
{simulation_requirement}

{f"Report context: {report_context[:500]}" if report_context else ""}

Break this question into at most {max_queries} sub-questions:
{query}"""

        try:
            response = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3
            )
            
            sub_queries = response.get("sub_queries", [])
            # Ensure it is a list of strings
            return [str(sq) for sq in sub_queries[:max_queries]]
            
        except Exception as e:
            logger.warning(t("console.generateSubQueriesFailed", error=str(e)))
            # Fallback: return variants based on the original question
            return [
                query,
                t('zepTools.subQueryParticipants', query=query),
                t('zepTools.subQueryCausesImpact', query=query),
                t('zepTools.subQueryDevelopment', query=query)
            ][:max_queries]
    
    def panorama_search(
        self,
        graph_id: str,
        query: str,
        include_expired: bool = True,
        limit: int = 50
    ) -> PanoramaResult:
        """
        [PanoramaSearch - breadth search]
        
        Get a full-picture view, including all related content and historical/expired info:
        1. Get all related nodes
        2. Get all edges (including expired/invalidated ones)
        3. Categorize currently valid vs. historical info
        
        Suited for scenarios needing the full picture of events or tracing their evolution.
        
        Args:
            graph_id: Graph ID
            query: Search query (for relevance ranking)
            include_expired: Whether to include expired content (default True)
            limit: Result count limit
            
        Returns:
            PanoramaResult: Breadth search result
        """
        logger.info(t("console.panoramaSearchStart", query=query[:50]))
        
        result = PanoramaResult(query=query)
        
        # A full graph scan makes this tool unusable on Zep Free plans. Use
        # Zep's relevance-ranked edge search as a bounded panorama instead.
        # It preserves the report's evidence-first behavior without loading
        # hundreds of unrelated nodes and relationship pages.
        search_result = self.search_graph(
            graph_id=graph_id,
            query=query,
            limit=limit,
            scope="edges",
        )
        result.active_facts = list(search_result.facts[:limit])
        result.active_count = len(result.active_facts)
        result.historical_facts = []
        result.historical_count = 0
        result.total_nodes = len(search_result.nodes)
        result.total_edges = len(search_result.edges)
        
        logger.info(t("console.panoramaSearchComplete", active=result.active_count, historical=result.historical_count))
        return result
    
    def quick_search(
        self,
        graph_id: str,
        query: str,
        limit: int = 10
    ) -> SearchResult:
        """
        [QuickSearch - simple search]
        
        Fast, lightweight retrieval tool:
        1. Directly calls Zep semantic search
        2. Returns the most relevant results
        3. Suited for simple, direct retrieval needs
        
        Args:
            graph_id: Graph ID
            query: Search query
            limit: Number of results to return
            
        Returns:
            SearchResult: Search result
        """
        logger.info(t("console.quickSearchStart", query=query[:50]))
        
        # Directly call the existing search_graph method
        result = self.search_graph(
            graph_id=graph_id,
            query=query,
            limit=limit,
            scope="edges"
        )
        
        logger.info(t("console.quickSearchComplete", count=result.total_count))
        return result
    
    def interview_agents(
        self,
        simulation_id: str,
        interview_requirement: str,
        simulation_requirement: str = "",
        max_agents: int = 5,
        custom_questions: List[str] = None
    ) -> InterviewResult:
        """
        [InterviewAgents - deep interview]
        
        Calls the real OASIS interview API to interview Agents running in the simulation:
        1. Automatically read profile files to learn about all simulated Agents
        2. Use LLM to analyze interview needs and smartly select the most relevant Agents
        3. Use LLM to generate interview questions
        4. Call /api/simulation/interview/batch for real interviews (both platforms simultaneously)
        5. Consolidate all interview results into an interview report
        
        [Important] Requires the simulation environment to be running (OASIS env not closed)
        
        [Use cases]
        - Understand views on events from different role perspectives
        - Collect opinions and viewpoints from multiple parties
        - Get real answers from simulated Agents (not LLM-simulated)
        
        Args:
            simulation_id: Simulation ID (to locate profile files and call the interview API)
            interview_requirement: Interview requirement description (unstructured, e.g. "understand students' views on the event")
            simulation_requirement: Simulation requirement background (optional)
            max_agents: Maximum number of Agents to interview
            custom_questions: Custom interview questions (optional; auto-generated if not provided)
            
        Returns:
            InterviewResult: Interview result
        """
        from .simulation_runner import SimulationRunner
        
        logger.info(t("console.interviewAgentsStart", requirement=interview_requirement[:50]))
        
        result = InterviewResult(
            interview_topic=interview_requirement,
            interview_questions=custom_questions or []
        )
        
        # Step 1: Read profile files
        profiles = self._load_agent_profiles(simulation_id)
        
        if not profiles:
            logger.warning(t("console.profilesNotFound", simId=simulation_id))
            result.summary = t('zepTools.noInterviewProfiles')
            return result
        
        result.total_agents = len(profiles)
        logger.info(t("console.loadedProfiles", count=len(profiles)))
        
        # Step 2: Use LLM to select Agents to interview (returns list of agent_ids)
        selected_agents, selected_indices, selection_reasoning = self._select_agents_for_interview(
            profiles=profiles,
            interview_requirement=interview_requirement,
            simulation_requirement=simulation_requirement,
            max_agents=max_agents
        )
        
        result.selected_agents = selected_agents
        result.selection_reasoning = selection_reasoning
        logger.info(t("console.selectedAgentsForInterview", count=len(selected_agents), indices=selected_indices))
        
        # Step 3: Generate interview questions (if not provided)
        if not result.interview_questions:
            result.interview_questions = self._generate_interview_questions(
                interview_requirement=interview_requirement,
                simulation_requirement=simulation_requirement,
                selected_agents=selected_agents
            )
            logger.info(t("console.generatedInterviewQuestions", count=len(result.interview_questions)))
        
        # Merge questions into a single interview prompt
        combined_prompt = "\n".join([f"{i+1}. {q}" for i, q in enumerate(result.interview_questions)])
        
        # Add optimization prefix to constrain Agent reply format
        INTERVIEW_PROMPT_PREFIX = (
            "You are being interviewed. Answer the following questions directly using your persona, past memories, and actions.\n"
            "Response requirements:\n"
            "1. Answer naturally; do not call tools.\n"
            "2. Do not return JSON or a tool-call format.\n"
            "3. Do not use Markdown headings.\n"
            "4. Answer each numbered question in order.\n"
            "5. Separate answers with blank lines.\n"
            "6. Give each answer substantive content of at least two sentences.\n\n"
        )
        optimized_prompt = f"{INTERVIEW_PROMPT_PREFIX}{combined_prompt}"
        
        # Step 4: Call the real interview API (no platform specified; both platforms by default)
        try:
            # Build batch interview list (no platform specified; both platforms)
            interviews_request = []
            for agent_idx in selected_indices:
                interviews_request.append({
                    "agent_id": agent_idx,
                    "prompt": optimized_prompt  # Use the optimized prompt
                    # No platform specified; the API interviews on both twitter and reddit
                })
            
            logger.info(t("console.callingBatchInterviewApi", count=len(interviews_request)))
            
            # Call SimulationRunner's batch interview method (no platform; both platforms)
            api_result = SimulationRunner.interview_agents_batch(
                simulation_id=simulation_id,
                interviews=interviews_request,
                platform=None,  # No platform specified; both platforms
                timeout=180.0   # Both platforms need a longer timeout
            )
            
            logger.info(t("console.interviewApiReturned", count=api_result.get('interviews_count', 0), success=api_result.get('success')))
            
            # Check whether the API call succeeded
            if not api_result.get("success", False):
                error_msg = api_result.get("error", t('zepTools.unknownError'))
                logger.warning(t("console.interviewApiReturnedFailure", error=error_msg))
                result.summary = t('zepTools.interviewApiFailed', error=error_msg)
                return result
            
            # Step 5: Parse API results and build AgentInterview objects
            # Dual-platform response format: {"twitter_0": {...}, "reddit_0": {...}, "twitter_1": {...}, ...}
            api_data = api_result.get("result", {})
            results_dict = api_data.get("results", {}) if isinstance(api_data, dict) else {}
            
            for i, agent_idx in enumerate(selected_indices):
                agent = selected_agents[i]
                agent_name = agent.get("realname", agent.get("username", f"Agent_{agent_idx}"))
                agent_role = agent.get("profession", t('zepTools.unknown'))
                agent_bio = agent.get("bio", "")
                
                # Get this Agent's interview results on both platforms
                twitter_result = results_dict.get(f"twitter_{agent_idx}", {})
                reddit_result = results_dict.get(f"reddit_{agent_idx}", {})
                
                twitter_response = twitter_result.get("response", "")
                reddit_response = reddit_result.get("response", "")

                # Strip possible tool-call JSON wrapping
                twitter_response = self._clean_tool_call_response(twitter_response)
                reddit_response = self._clean_tool_call_response(reddit_response)

                # Always output dual-platform markers
                twitter_text = twitter_response if twitter_response else t('zepTools.noPlatformResponse')
                reddit_text = reddit_response if reddit_response else t('zepTools.noPlatformResponse')
                response_text = t('zepTools.platformResponses', twitter=twitter_text, reddit=reddit_text)

                # Extract key quotes (from both platforms' answers)
                import re
                combined_responses = f"{twitter_response} {reddit_response}"

                # Clean response text: remove markers, numbering, Markdown and other noise
                clean_text = re.sub(r'#{1,6}\s+', '', combined_responses)
                clean_text = re.sub(r'\{[^}]*tool_name[^}]*\}', '', clean_text)
                clean_text = re.sub(r'[*_`|>~\-]{2,}', '', clean_text)
                clean_text = re.sub(r'(?:Question|คำถาม)\s*\d+[：:]\s*', '', clean_text, flags=re.IGNORECASE)
                clean_text = re.sub(r'【[^】]+】', '', clean_text)

                # Strategy 1 (primary): extract complete substantive sentences
                sentences = re.split(r'[。！？]', clean_text)
                meaningful = [
                    s.strip() for s in sentences
                    if 20 <= len(s.strip()) <= 150
                    and not re.match(r'^[\s\W，,；;：:、]+', s.strip())
                    and not re.match(r'(?:\{|Question|คำถาม)', s.strip(), flags=re.IGNORECASE)
                ]
                meaningful.sort(key=len, reverse=True)
                key_quotes = meaningful[:3]

                # Strategy 2 (supplementary): long text inside properly paired Chinese quote marks
                if not key_quotes:
                    paired = re.findall(r'\u201c([^\u201c\u201d]{15,100})\u201d', clean_text)
                    paired += re.findall(r'\u300c([^\u300c\u300d]{15,100})\u300d', clean_text)
                    key_quotes = [q for q in paired if not re.match(r'^[，,；;：:、]', q)][:3]
                
                interview = AgentInterview(
                    agent_name=agent_name,
                    agent_role=agent_role,
                    agent_bio=agent_bio[:1000],  # Increased bio length limit
                    question=combined_prompt,
                    response=response_text,
                    key_quotes=key_quotes[:5]
                )
                result.interviews.append(interview)
            
            result.interviewed_count = len(result.interviews)
            
        except ValueError as e:
            # Simulation environment not running
            safe_error = t('zepTools.interviewEnvironmentClosed')
            logger.warning(t("console.interviewApiCallFailed", error=safe_error))
            result.summary = t('zepTools.interviewUnavailable', error=safe_error)
            return result
        except Exception as e:
            safe_error = t('zepTools.interviewRequestFailed')
            logger.error(t("console.interviewApiCallException", error=safe_error))
            import traceback
            logger.error(traceback.format_exc())
            result.summary = t('zepTools.interviewError', error=safe_error)
            return result
        
        # Step 6: Generate interview summary
        if result.interviews:
            result.summary = self._generate_interview_summary(
                interviews=result.interviews,
                interview_requirement=interview_requirement
            )
        
        logger.info(t("console.interviewAgentsComplete", count=result.interviewed_count))
        return result
    
    @staticmethod
    def _clean_tool_call_response(response: str) -> str:
        """Strip JSON tool-call wrapping from Agent replies and extract the actual content"""
        if not response or not response.strip().startswith('{'):
            return response
        text = response.strip()
        if 'tool_name' not in text[:80]:
            return response
        import re as _re
        try:
            data = json.loads(text)
            if isinstance(data, dict) and 'arguments' in data:
                for key in ('content', 'text', 'body', 'message', 'reply'):
                    if key in data['arguments']:
                        return str(data['arguments'][key])
        except (json.JSONDecodeError, KeyError, TypeError):
            match = _re.search(r'"content"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
            if match:
                return match.group(1).replace('\\n', '\n').replace('\\"', '"')
        return response

    def _load_agent_profiles(self, simulation_id: str) -> List[Dict[str, Any]]:
        """Load the simulation's Agent profile files"""
        import os
        import csv
        
        # Build profile file path
        sim_dir = os.path.join(
            os.path.dirname(__file__), 
            f'../../uploads/simulations/{simulation_id}'
        )
        
        profiles = []
        
        # Prefer reading Reddit JSON format
        reddit_profile_path = os.path.join(sim_dir, "reddit_profiles.json")
        if os.path.exists(reddit_profile_path):
            try:
                with open(reddit_profile_path, 'r', encoding='utf-8') as f:
                    profiles = json.load(f)
                logger.info(t("console.loadedRedditProfiles", count=len(profiles)))
                return profiles
            except Exception as e:
                logger.warning(t("console.readRedditProfilesFailed", error=e))
        
        # Try reading Twitter CSV format
        twitter_profile_path = os.path.join(sim_dir, "twitter_profiles.csv")
        if os.path.exists(twitter_profile_path):
            try:
                with open(twitter_profile_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        # Convert CSV format to unified format
                        profiles.append({
                            "realname": row.get("name", ""),
                            "username": row.get("username", ""),
                            "bio": row.get("description", ""),
                            "persona": row.get("user_char", ""),
                            "profession": t('zepTools.unknown')
                        })
                logger.info(t("console.loadedTwitterProfiles", count=len(profiles)))
                return profiles
            except Exception as e:
                logger.warning(t("console.readTwitterProfilesFailed", error=e))
        
        return profiles
    
    def _select_agents_for_interview(
        self,
        profiles: List[Dict[str, Any]],
        interview_requirement: str,
        simulation_requirement: str,
        max_agents: int
    ) -> tuple:
        """
        Use LLM to select Agents to interview
        
        Returns:
            tuple: (selected_agents, selected_indices, reasoning)
                - selected_agents: Full info list of selected Agents
                - selected_indices: Index list of selected Agents (for API calls)
                - reasoning: Selection reasoning
        """
        
        # Build Agent summary list
        agent_summaries = []
        for i, profile in enumerate(profiles):
            summary = {
                "index": i,
                "name": profile.get("realname", profile.get("username", f"Agent_{i}")),
                "profession": profile.get("profession", t('zepTools.unknown')),
                "bio": profile.get("bio", "")[:200],
                "interested_topics": profile.get("interested_topics", [])
            }
            agent_summaries.append(summary)
        
        system_prompt = f"""You are an interview producer. Select the simulation agents best suited to answer an interview request.

Selection criteria:
1. Their identity or profession is relevant to the topic.
2. They may offer distinct or valuable perspectives.
3. Include diverse perspectives when relevant.
4. Prefer agents directly related to the event.

Return JSON only:
{{"selected_indices": [0, 1], "reasoning": "brief reason"}}

{get_language_instruction()}"""

        user_prompt = f"""Interview request:
{interview_requirement}

Simulation background:
{simulation_requirement or t('zepTools.notProvided')}

Available agents ({len(agent_summaries)} total):
{json.dumps(agent_summaries, ensure_ascii=False, indent=2)}

Select at most {max_agents} suitable agents and explain why."""

        try:
            response = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3
            )
            
            selected_indices = response.get("selected_indices", [])[:max_agents]
            reasoning = response.get("reasoning", t('zepTools.autoSelectedByRelevance'))
            
            # Get full info of selected Agents
            selected_agents = []
            valid_indices = []
            for idx in selected_indices:
                if 0 <= idx < len(profiles):
                    selected_agents.append(profiles[idx])
                    valid_indices.append(idx)
            
            return selected_agents, valid_indices, reasoning
            
        except Exception as e:
            logger.warning(t("console.llmSelectAgentFailed", error=e))
            # Fallback: select the first N
            selected = profiles[:max_agents]
            indices = list(range(min(max_agents, len(profiles))))
            return selected, indices, t('zepTools.defaultSelectionStrategy')
    
    def _generate_interview_questions(
        self,
        interview_requirement: str,
        simulation_requirement: str,
        selected_agents: List[Dict[str, Any]]
    ) -> List[str]:
        """Use LLM to generate interview questions"""
        
        agent_roles = [a.get("profession", t('zepTools.unknown')) for a in selected_agents]
        
        system_prompt = f"""You are a professional interviewer. Generate 3–5 focused interview questions.

Requirements:
1. Use open questions that invite detailed answers.
2. Adapt questions to the selected roles.
3. Cover facts, views, and lived experience.
4. Ask directly without background exposition or prefixes.
5. Keep each question concise.
6. Return JSON only: {{"questions": ["question 1", "question 2"]}}.

{get_language_instruction()}"""

        user_prompt = f"""Interview request: {interview_requirement}

Simulation background: {simulation_requirement or t('zepTools.notProvided')}

Selected roles: {', '.join(agent_roles)}

Generate 3–5 interview questions."""

        try:
            response = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.5
            )
            
            return response.get("questions", [t('zepTools.interviewFallbackQuestion', topic=interview_requirement)])
            
        except Exception as e:
            logger.warning(t("console.generateInterviewQuestionsFailed", error=e))
            return [
                t('zepTools.interviewFallbackQuestion', topic=interview_requirement),
                t('zepTools.interviewFallbackImpact'),
                t('zepTools.interviewFallbackImprovement'),
            ]
    
    def _generate_interview_summary(
        self,
        interviews: List[AgentInterview],
        interview_requirement: str
    ) -> str:
        """Generate interview summary"""
        
        if not interviews:
            return t('zepTools.noCompletedInterviews')
        
        # Collect all interview content
        interview_texts = []
        for interview in interviews:
            interview_texts.append(f"[{interview.agent_name} ({interview.agent_role})]\n{interview.response[:500]}")
        
        system_prompt = f"""You are a professional news editor. Create a neutral interview summary from multiple respondents.

Requirements:
1. Extract each viewpoint, consensus, and disagreement.
2. Include only valuable quotations.
3. Keep the summary under 1,000 words.
4. Use plain text paragraphs only: no headings or divider lines.
5. Use quotation marks for verbatim quotations.

{get_language_instruction()}"""

        user_prompt = f"""Interview topic: {interview_requirement}

Interview material:
{"".join(interview_texts)}

Write the interview summary."""

        try:
            summary = self.llm.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=800
            )
            return summary
            
        except Exception as e:
            logger.warning(t("console.generateInterviewSummaryFailed", error=e))
            # Fallback: simple concatenation
            return t('zepTools.interviewSummaryFallback', count=len(interviews), names=', '.join(i.agent_name for i in interviews))
