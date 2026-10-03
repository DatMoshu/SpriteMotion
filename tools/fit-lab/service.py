"""Small, stable discovery boundary for desktop editors and webview hosts."""


def describe(pack):
    return {
        'schema': 'spritemotion.fit-lab-service',
        'schema_version': 1,
        'pack': pack,
        'capabilities': ['revision-saves', 'three-backups', 'scoped-fits', 'blender-builds', 'render-index'],
    }
