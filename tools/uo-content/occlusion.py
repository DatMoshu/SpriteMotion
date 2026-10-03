"""Camera-depth holdout with bounded, side-specific garment contact tolerance.

The occluder is a pristine animated body, independent of hide-body geometry.
Only the nearest garment surface can claim a contact exemption, and only
against the same anatomical region within the configured penetration depth.
"""
import numpy as np


def region(name):
    base, dot, side = name.partition('.')
    base = {'upper_arm_twist': 'upper_arm', 'forearm_twist': 'forearm',
            'toe': 'foot'}.get(base, base)
    if base.startswith('finger'):
        base = 'hand'
    return base + (dot + side if dot else '')


def triangle_regions(obj):
    """Dominant summed skin weight per triangle, preserving left/right identity."""
    mesh = obj.data
    mesh.calc_loop_triangles()
    names = [region(g.name) for g in obj.vertex_groups]
    result = []
    for tri in mesh.loop_triangles:
        weights = {}
        for index in tri.vertices:
            for group in mesh.vertices[index].groups:
                name = names[group.group]
                weights[name] = weights.get(name, 0.0) + group.weight
        result.append(max(weights, key=weights.get) if weights else '')
    return np.asarray(result)


def blocked_pixels(body_depth, item_depth, margin, contacts=(), tolerance=0.0):
    """A contact is a pair of depth maps for ONE matching body/item region.

    Maps belonging to a hidden rear item must not exempt a nearer visible item.
    Infinite background depths never establish contact.
    """
    allowance = np.full(body_depth.shape, margin, dtype=float)
    for own_body, own_item in contacts:
        same_surface = (np.isfinite(own_body) & np.isfinite(own_item)
                        & np.isclose(own_body, body_depth, rtol=0, atol=1e-6)
                        & np.isclose(own_item, item_depth, rtol=0, atol=1e-6))
        allowance[same_surface] = max(margin, tolerance)
    return np.isfinite(body_depth) & (body_depth + allowance < item_depth)


class BodyHoldout:
    def __init__(self, body, pristine_mesh, objects):
        import bpy
        self.body = body.copy()
        self.body.data = pristine_mesh
        self.body.name = 'SpriteMotion_DepthBody'
        bpy.context.scene.collection.objects.link(self.body)
        self.body.hide_render = True
        self.body_regions = triangle_regions(self.body)
        self.items = [(obj, triangle_regions(obj)) for obj in objects]
        self.mode = 'clothing'
        self.tolerance = 0.0

    def configure(self, mode, hide):
        self.mode = mode
        self.tolerance = float(hide.get('inward', .01)) if hide.get('enabled') else 0.0

    def render(self, env, free, margin):
        raster = env['raster']
        coverage, body_depth = raster([self.body])
        if self.mode == 'none':
            return free.copy(), coverage
        visible = [(obj, labels) for obj, labels in self.items if not obj.hide_render]
        _, item_depth = raster([obj for obj, _ in visible])
        # Match the renderer's treatment of antialiased edge samples missed by
        # pixel-centre rasterization. Missing samples receive no own-part exemption.
        seen = free[..., 3] >= .5
        for _ in range(2):
            missing = seen & ~np.isfinite(item_depth)
            if not missing.any():
                break
            h, w = item_depth.shape
            pad = np.pad(item_depth, 1, constant_values=np.inf)
            neighbours = np.minimum.reduce([pad[y:y+h, x:x+w] for y in range(3) for x in range(3)])
            item_depth = np.where(missing, neighbours, item_depth)

        def contacts():
            if self.mode != 'clothing' or self.tolerance <= margin:
                return
            for name in sorted(set(self.body_regions) - {''}):
                matching = [(obj, labels == name) for obj, labels in visible if np.any(labels == name)]
                if not matching:
                    continue
                _, own_body = raster([self.body], self.body_regions == name)
                own_item = np.full(item_depth.shape, np.inf)
                for obj, mask in matching:
                    _, depth = raster([obj], mask)
                    own_item = np.minimum(own_item, depth)
                yield own_body, own_item

        blocked = blocked_pixels(body_depth, item_depth, margin, contacts(), self.tolerance)
        hold = free.copy()
        hold[blocked] = 0
        return hold, coverage
