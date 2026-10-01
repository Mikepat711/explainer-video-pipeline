from .assemble import Assemble
from .captions import Captions
from .mix import Mix
from .music import Music
from .plan import Plan
from .qa import QA
from .render import Render
from .research import Research
from .script import Script
from .shots import Shots
from .timeline import Timeline
from .voice import Voice

ORDER = [Research(), Script(), Plan(), Shots(), Voice(), Timeline(), Render(), Music(), Mix(), Captions(),
         Assemble(), QA()]
REGISTRY = {s.name: s for s in ORDER}
