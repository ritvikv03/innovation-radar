import networkx as nx
import json
import os
from datetime import datetime
from difflib import SequenceMatcher
import math

# ===========================
# CONFIGURATION CONSTANTS
# ===========================

# Entity Resolution: Similarity threshold for merging nodes (0.0 - 1.0)
SIMILARITY_THRESHOLD = 0.85

# Temporal Decay: Half-life in days (how long until weight decays to 50%)
DECAY_HALF_LIFE_DAYS = 90

# Provenance: Minimum required fields for edge validation
REQUIRED_EDGE_FIELDS = ['source_url', 'exact_quote', 'timestamp']

# ===========================
# UTILITY FUNCTIONS
# ===========================

def calculate_similarity(str1, str2):
    """
    Calculate similarity ratio between two strings using SequenceMatcher.
    Returns: float [0.0 - 1.0] where 1.0 is identical.
    """
    return SequenceMatcher(None, str1.lower(), str2.lower()).ratio()


def calculate_temporal_decay(timestamp_str, current_time=None):
    """
    Calculate decay factor based on exponential decay formula.

    Formula: decay_factor = 0.5^(age_days / half_life_days)

    Args:
        timestamp_str: ISO format timestamp string (e.g., "2024-03-15T10:30:00")
        current_time: Optional datetime object for testing (defaults to now)

    Returns:
        float: Decay multiplier [0.0 - 1.0]
    """
    from datetime import timezone

    if current_time is None:
        current_time = datetime.now(timezone.utc)

    try:
        event_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        # Ensure current_time is timezone-aware if event_time is
        if event_time.tzinfo is not None and current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)
        elif event_time.tzinfo is None and current_time.tzinfo is not None:
            event_time = event_time.replace(tzinfo=timezone.utc)

        age_days = (current_time - event_time).total_seconds() / 86400  # Convert to days

        # Exponential decay: 0.5^(age / half_life)
        decay_factor = math.pow(0.5, age_days / DECAY_HALF_LIFE_DAYS)

        # Clamp to [0.0, 1.0]
        return max(0.0, min(1.0, decay_factor))
    except (ValueError, AttributeError):
        # If timestamp is invalid, return minimum decay
        return 0.1


def find_similar_node(G, candidate_label, category, similarity_threshold=SIMILARITY_THRESHOLD):
    """
    Search for existing nodes with similar labels in the same category.

    Args:
        G: NetworkX graph
        candidate_label: Label of potential new node
        category: PESTEL-EL category
        similarity_threshold: Minimum similarity to consider a match

    Returns:
        str or None: Existing node ID if found, else None
    """
    for node_id, attrs in G.nodes(data=True):
        existing_label = attrs.get('label', '')
        existing_category = attrs.get('category', '')

        # Only compare nodes in the same category
        if existing_category == category:
            similarity = calculate_similarity(candidate_label, existing_label)
            if similarity >= similarity_threshold:
                return node_id

    return None


def validate_edge_provenance(edge_data):
    """
    Validate that edge contains required provenance fields.

    Args:
        edge_data: Dictionary containing edge properties

    Returns:
        tuple: (is_valid: bool, error_message: str or None)
    """
    missing_fields = []

    for field in REQUIRED_EDGE_FIELDS:
        if field not in edge_data or not edge_data[field]:
            missing_fields.append(field)

    if missing_fields:
        return False, f"Missing required provenance fields: {', '.join(missing_fields)}"

    # Validate exact_quote is substantial (at least 10 characters)
    if len(edge_data.get('exact_quote', '')) < 10:
        return False, "exact_quote must be at least 10 characters to verify provenance"

    # Validate source_url is a reasonable URL format
    source_url = edge_data.get('source_url', '')
    if not (source_url.startswith('http://') or source_url.startswith('https://')):
        return False, "source_url must be a valid HTTP/HTTPS URL"

    return True, None


def apply_decay_to_graph(G):
    """
    Apply temporal decay to all edges in the graph based on their timestamps.
    Updates edge weights in-place.

    Args:
        G: NetworkX graph

    Returns:
        dict: Statistics about decay application
    """
    current_time = datetime.now()
    stats = {
        'total_edges': 0,
        'edges_decayed': 0,
        'edges_removed': 0,
        'avg_decay_factor': 0.0
    }

    edges_to_remove = []
    decay_factors = []

    for source, target, key, attrs in G.edges(data=True, keys=True):
        stats['total_edges'] += 1

        if 'timestamp' in attrs and 'original_weight' in attrs:
            decay_factor = calculate_temporal_decay(attrs['timestamp'], current_time)
            decay_factors.append(decay_factor)

            # Apply decay to weight
            original_weight = attrs['original_weight']
            new_weight = original_weight * decay_factor

            # Remove edges that have decayed below threshold (< 0.05)
            if abs(new_weight) < 0.05:
                edges_to_remove.append((source, target, key))
                stats['edges_removed'] += 1
            else:
                G[source][target][key]['weight'] = new_weight
                G[source][target][key]['decay_factor'] = decay_factor
                stats['edges_decayed'] += 1

    # Remove decayed edges
    for edge in edges_to_remove:
        G.remove_edge(edge[0], edge[1], key=edge[2])

    if decay_factors:
        stats['avg_decay_factor'] = sum(decay_factors) / len(decay_factors)

    return stats


# ===========================
# MAIN GRAPH OPERATIONS
# ===========================

def update_graph(source_label, target_label, relationship, pillar,
                 source_url, exact_quote, timestamp=None, weight=1.0,
                 source_category=None, target_category=None,
                 source_metadata=None, target_metadata=None):
    """
    Update Knowledge Graph with entity resolution, temporal decay, and provenance validation.

    Args:
        source_label: Human-readable label for source node
        target_label: Human-readable label for target node
        relationship: Type of relationship (INCREASES, DECREASES, REGULATES, etc.)
        pillar: PESTEL-EL pillar for categorization
        source_url: URL of the source document (REQUIRED for provenance)
        exact_quote: Verbatim quote from source justifying the link (REQUIRED)
        timestamp: ISO format timestamp (defaults to current time)
        weight: Impact magnitude [-1.0 to 1.0] (defaults to 1.0)
        source_category: Override category for source node
        target_category: Override category for target node
        source_metadata: Additional metadata for source node
        target_metadata: Additional metadata for target node

    Returns:
        dict: Operation result with status and details
    """
    graph_path = './data/graph.json'

    # Set default timestamp
    if timestamp is None:
        timestamp = datetime.now().isoformat()

    # Validate provenance FIRST (Hallucination Defense)
    edge_data = {
        'source_url': source_url,
        'exact_quote': exact_quote,
        'timestamp': timestamp
    }
    is_valid, error_msg = validate_edge_provenance(edge_data)
    if not is_valid:
        return {
            'status': 'REJECTED',
            'reason': f'Provenance validation failed: {error_msg}',
            'source': source_label,
            'target': target_label
        }

    # Load or create graph
    if os.path.exists(graph_path):
        with open(graph_path, 'r') as f:
            data = json.load(f)
            G = nx.node_link_graph(data)
    else:
        os.makedirs('./data', exist_ok=True)
        G = nx.MultiDiGraph()

    # Determine categories (default to pillar if not specified)
    source_category = source_category or pillar
    target_category = target_category or pillar

    # ENTITY RESOLUTION: Check for similar existing nodes
    existing_source = find_similar_node(G, source_label, source_category)
    existing_target = find_similar_node(G, target_label, target_category)

    # Use existing node IDs or create new ones
    if existing_source:
        source_id = existing_source
        source_action = 'MERGED'
    else:
        # Generate new node ID
        source_id = f"{source_category.upper()[:4]}_{hash(source_label) % 10000:04d}"
        source_action = 'CREATED'

        # Add source node with metadata
        node_attrs = {
            'label': source_label,
            'category': source_category,
            'created_at': timestamp,
            'source': source_url
        }
        if source_metadata:
            node_attrs.update(source_metadata)
        G.add_node(source_id, **node_attrs)

    if existing_target:
        target_id = existing_target
        target_action = 'MERGED'
    else:
        target_id = f"{target_category.upper()[:4]}_{hash(target_label) % 10000:04d}"
        target_action = 'CREATED'

        node_attrs = {
            'label': target_label,
            'category': target_category,
            'created_at': timestamp,
            'source': source_url
        }
        if target_metadata:
            node_attrs.update(target_metadata)
        G.add_node(target_id, **node_attrs)

    # Add edge with full provenance
    edge_attrs = {
        'relationship': relationship,
        'pillar': pillar,
        'original_weight': weight,  # Store original for decay calculation
        'weight': weight,
        'timestamp': timestamp,
        'source_url': source_url,
        'exact_quote': exact_quote,
        'decay_factor': 1.0  # Initially no decay
    }

    G.add_edge(source_id, target_id, **edge_attrs)

    # Apply temporal decay to entire graph
    decay_stats = apply_decay_to_graph(G)

    # Save back to JSON with proper node_link format
    graph_data = nx.node_link_data(G)

    with open(graph_path, 'w') as f:
        json.dump(graph_data, f, indent=2)

    return {
        'status': 'SUCCESS',
        'source_id': source_id,
        'source_action': source_action,
        'target_id': target_id,
        'target_action': target_action,
        'relationship': relationship,
        'decay_stats': decay_stats,
        'message': f"Successfully linked {source_label} ({source_action}) to {target_label} ({target_action})"
    }


def query_graph(node_id=None, category=None, min_weight=0.1):
    """
    Query the Knowledge Graph with filters.

    Args:
        node_id: Specific node to query
        category: Filter by PESTEL-EL category
        min_weight: Minimum edge weight threshold (after decay)

    Returns:
        dict: Query results
    """
    graph_path = './data/graph.json'

    if not os.path.exists(graph_path):
        return {'status': 'ERROR', 'message': 'Graph does not exist'}

    with open(graph_path, 'r') as f:
        data = json.load(f)
        G = nx.node_link_graph(data)

    results = {
        'nodes': [],
        'edges': [],
        'stats': {
            'total_nodes': G.number_of_nodes(),
            'total_edges': G.number_of_edges()
        }
    }

    # Filter nodes
    for node_id_iter, attrs in G.nodes(data=True):
        if node_id and node_id_iter != node_id:
            continue
        if category and attrs.get('category') != category:
            continue

        results['nodes'].append({
            'id': node_id_iter,
            **attrs
        })

    # Filter edges
    for source, target, attrs in G.edges(data=True):
        if attrs.get('weight', 0) < min_weight:
            continue

        results['edges'].append({
            'source': source,
            'target': target,
            **attrs
        })

    return results


if __name__ == "__main__":
    # CLI interface for Analyst agent
    import argparse

    parser = argparse.ArgumentParser(description='Fendt PESTEL-EL Knowledge Graph Utilities')
    parser.add_argument('--source', required=True, help='Source node label')
    parser.add_argument('--target', required=True, help='Target node label')
    parser.add_argument('--relationship', required=True, help='Relationship type')
    parser.add_argument('--pillar', required=True, help='PESTEL-EL pillar')
    parser.add_argument('--source-url', required=True, help='Source URL for provenance')
    parser.add_argument('--exact-quote', required=True, help='Exact quote from source')
    parser.add_argument('--timestamp', help='ISO timestamp (optional)')
    parser.add_argument('--weight', type=float, default=1.0, help='Edge weight [-1.0 to 1.0]')
    parser.add_argument('--source-category', help='Source node category')
    parser.add_argument('--target-category', help='Target node category')

    args = parser.parse_args()

    result = update_graph(
        source_label=args.source,
        target_label=args.target,
        relationship=args.relationship,
        pillar=args.pillar,
        source_url=args.source_url,
        exact_quote=args.exact_quote,
        timestamp=args.timestamp,
        weight=args.weight,
        source_category=args.source_category,
        target_category=args.target_category
    )

    print(json.dumps(result, indent=2))
