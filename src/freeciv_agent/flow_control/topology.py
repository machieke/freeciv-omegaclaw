"""Topology indexes that enforce query-local generation safety."""

from .model import FlowProcess, FlowView


class FlowTopologyIndex:
    """Stable and local indexes for one immutable :class:`FlowView`."""

    def __init__(self, view):
        if not isinstance(view, FlowView):
            raise TypeError("topology index requires FlowView")
        self.view = view
        self._nodes = dict(
            (row.stable_id, row) for row in view.nodes)
        self._edges = dict(
            (row.stable_id, row) for row in view.edges)
        self._outgoing = {}
        self._incoming = {}
        for edge in view.edges:
            self._outgoing.setdefault(
                edge.source_node_id, []).append(edge)
            self._incoming.setdefault(
                edge.target_node_id, []).append(edge)
        for values in self._outgoing.values():
            values.sort(key=lambda row: row.stable_id)
        for values in self._incoming.values():
            values.sort(key=lambda row: row.stable_id)

    def node(self, stable_id):
        return self._nodes[str(stable_id)]

    def edge(self, stable_id):
        return self._edges[str(stable_id)]

    def resolve(self, handle):
        return self.view.resolve(handle)

    def outgoing(self, stable_id, process=None):
        values = tuple(
            self._outgoing.get(str(stable_id), ()))
        if process is None:
            return values
        if not isinstance(process, FlowProcess):
            process = FlowProcess(process)
        return tuple(
            edge for edge in values
            if edge.legality.allows(process))

    def incoming(self, stable_id, process=None):
        values = tuple(
            self._incoming.get(str(stable_id), ()))
        if process is None:
            return values
        if not isinstance(process, FlowProcess):
            process = FlowProcess(process)
        return tuple(
            edge for edge in values
            if edge.legality.allows(process))
