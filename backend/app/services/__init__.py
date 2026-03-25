"""
Business services module
"""

__all__ = [
    'OntologyGenerator', 
    'GraphBuilderService', 
    'TextProcessor',
    'ZepEntityReader',
    'EntityNode',
    'FilteredEntities',
    'OasisProfileGenerator',
    'OasisAgentProfile',
    'SimulationManager',
    'SimulationState',
    'SimulationStatus',
    'SimulationConfigGenerator',
    'SimulationParameters',
    'AgentActivityConfig',
    'TimeSimulationConfig',
    'EventConfig',
    'PlatformConfig',
    'SimulationRunner',
    'SimulationRunState',
    'RunnerStatus',
    'AgentAction',
    'RoundSummary',
    'ZepGraphMemoryUpdater',
    'ZepGraphMemoryManager',
    'AgentActivity',
    'SimulationIPCClient',
    'SimulationIPCServer',
    'IPCCommand',
    'IPCResponse',
    'CommandType',
    'CommandStatus',
]

_EXPORT_TO_MODULE = {
    'OntologyGenerator': '.ontology_generator',
    'GraphBuilderService': '.graph_builder',
    'TextProcessor': '.text_processor',
    'ZepEntityReader': '.zep_entity_reader',
    'EntityNode': '.zep_entity_reader',
    'FilteredEntities': '.zep_entity_reader',
    'OasisProfileGenerator': '.oasis_profile_generator',
    'OasisAgentProfile': '.oasis_profile_generator',
    'SimulationManager': '.simulation_manager',
    'SimulationState': '.simulation_manager',
    'SimulationStatus': '.simulation_manager',
    'SimulationConfigGenerator': '.simulation_config_generator',
    'SimulationParameters': '.simulation_config_generator',
    'AgentActivityConfig': '.simulation_config_generator',
    'TimeSimulationConfig': '.simulation_config_generator',
    'EventConfig': '.simulation_config_generator',
    'PlatformConfig': '.simulation_config_generator',
    'SimulationRunner': '.simulation_runner',
    'SimulationRunState': '.simulation_runner',
    'RunnerStatus': '.simulation_runner',
    'AgentAction': '.simulation_runner',
    'RoundSummary': '.simulation_runner',
    'ZepGraphMemoryUpdater': '.zep_graph_memory_updater',
    'ZepGraphMemoryManager': '.zep_graph_memory_updater',
    'AgentActivity': '.zep_graph_memory_updater',
    'SimulationIPCClient': '.simulation_ipc',
    'SimulationIPCServer': '.simulation_ipc',
    'IPCCommand': '.simulation_ipc',
    'IPCResponse': '.simulation_ipc',
    'CommandType': '.simulation_ipc',
    'CommandStatus': '.simulation_ipc',
}


def __getattr__(name):
    module_name = _EXPORT_TO_MODULE.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    from importlib import import_module

    module = import_module(module_name, __name__)
    return getattr(module, name)

