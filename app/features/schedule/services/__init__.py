"""Schedule application services.

Public responsibilities:
- blocks: schedule validation and block workflows
- procedures: procedure creation and updates
- sync: external integration synchronization
- presentation: UI and export read models
- export: CSV/XLSX serialization

`_block_commands` is an internal mutation helper used only by `blocks`.
"""
