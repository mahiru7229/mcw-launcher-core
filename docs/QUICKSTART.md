# Quickstart

## Create a core facade

```python
from mcw_core import get_default_core
core = get_default_core()
```

## List instances

```python
from mcw_core.api.instance.instance_manager import InstanceManager
for instance in InstanceManager.list_instances():
    print(instance.name, instance.version_id)
```

## Launch with progress

```python
from mcw_core import get_default_core, LaunchRequest

def on_progress(event):
    print(event.stage, event.message, event.percentage)

core = get_default_core()
result = core.launch(LaunchRequest(instance=instance, account=account, authentication=authentication, progress_callback=on_progress))
```
