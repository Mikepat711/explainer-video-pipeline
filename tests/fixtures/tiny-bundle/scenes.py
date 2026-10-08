from lib import *


def hook(c, t, T):
    a = fade(t, 0.0, 0.3)
    text(c, "Tiny bundle", 960, 480, 72, WHITE, a, "bold")
    text(c, "smoke test", 960, 560, 40, CYAN, a, "semi")


SCENE_FUNCS = {"hook": hook}
