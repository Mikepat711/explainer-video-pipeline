from __future__ import annotations

from .. import offline, sources
from ..claude import ClaudeError
from ..pipeline import Stage
from ..plan.checks import check_research
from ..plan.docs import offline_research_markdown, research_markdown
from ..plan.prompts import research_prompt
from ..plan.schemas import RESEARCH
from ..util import log, write_json
from ..writer import banner, fallback_is_stale, get_writer, require_claude, write_meta, writer_identity
from .common import dir_fingerprint, optional_file


class Research(Stage):
    name = "research"
    scope = "common"
    description = "research the topic (Claude; Wikipedia only as a last resort)"
    extra_code = ("offline.py", "sources.py", "claude.py", "writer.py", "plan")

    def inputs(self, ctx):
        return {"topic": ctx.topic, "urls": ctx.source_urls, "cfg": ctx.cfg["research"],
                "writer": writer_identity(ctx.cfg), "web": ctx.cfg["llm"].get("web_research", True),
                "pack": dir_fingerprint(ctx.topic_dir / "sources"),
                "urls_file": optional_file(ctx.topic_dir / "sources.txt"),
                "override": optional_file(ctx.pack_file("research.md")),
                "hand_script": optional_file(ctx.pack_file("script.md")), "brief": ctx.brief.inputs()}

    def outputs(self, ctx):
        c = ctx.common
        return [c / "research.md", c / "research.json", c / "sources.json", c / "research.meta.json"]

    def still_fresh(self, ctx):
        return not fallback_is_stale(ctx.common, self.name, ctx.cfg)

    def run(self, ctx):
        c = ctx.common
        override = ctx.pack_file("research.md")
        local = sources.local_docs(ctx.topic_dir, ctx.source_urls)
        write_json(c / "sources.json", [{"name": d["name"], "origin": d["origin"], "chars": len(d["text"])}
                                        for d in local])
        if override or ctx.pack_file("script.md"):
            if override:
                log("    using hand-authored research.md from topic pack")
                md = override.read_text()
            else:
                log("    topic pack has a hand-authored script; summarising its sources offline")
                facts = offline.extract_facts(ctx.topic, local, ctx.cfg["research"]["max_facts"]) if local else []
                md = offline.research_markdown(ctx.topic, facts, local)
            (c / "research.md").write_text(md)
            write_json(c / "research.json", {"mode": "topic-pack", "topic": ctx.topic})
            write_meta(c, self.name, "topic-pack")
            return
        writer, reason = get_writer(ctx.cfg)
        if writer:
            try:
                brief, meta = writer.generate("research", research_prompt(ctx.topic, local, ctx.brief), RESEARCH,
                                              check=lambda r: check_research(r, ctx.brief.ids), web=True)
                write_json(c / "research.json", {"mode": "claude", **brief})
                (c / "research.md").write_text(research_markdown(brief))
                write_meta(c, self.name, **meta)
                log(f"    {len(brief['key_concepts'])} key concepts, {len(brief['numbers'])} numbers, "
                    f"{len(brief['sources'])} sources")
                return
            except ClaudeError as exc:
                reason = str(exc)
        require_claude(ctx, self.name, reason)
        banner(self.name, reason)
        docs = local or sources.gather(ctx.topic, ctx.topic_dir, [], ctx.cfg["research"]["fetch_wikipedia"])
        if not docs:
            raise SystemExit("no sources for the fallback writer: fix the Claude CLI, add files under "
                             "topics/<slug>/sources/, or pass --source URL")
        write_json(c / "sources.json", [{"name": d["name"], "origin": d["origin"], "chars": len(d["text"])}
                                        for d in docs])
        sections = offline.teaching_sections(docs)
        write_json(c / "research.json", {"mode": "offline", "topic": ctx.topic, "sections": sections})
        (c / "research.md").write_text(offline_research_markdown(ctx.topic, sections, docs))
        write_meta(c, self.name, "offline", fallback=True, reason=reason,
                   sources=[d["origin"] for d in docs])
