"""Read-only documentation and example downloads. No arbitrary file access."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from .config import PROJECT_ROOT

router = APIRouter(tags=["developer"])
DOC_HEADERS = {"Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff"}


class MarkdownResponse(PlainTextResponse):
    media_type = "text/markdown"


@router.get("/api/docs/markdown", response_class=MarkdownResponse,
            summary="完整接入文档（Markdown）", operation_id="getDeveloperMarkdown")
def markdown_docs():
    return MarkdownResponse((PROJECT_ROOT / "API.md").read_text(encoding="utf-8"),
                            headers=DOC_HEADERS)


@router.get("/llms.txt", response_class=PlainTextResponse,
            summary="Agent 接入索引", operation_id="getAgentIndex")
def agent_index():
    return PlainTextResponse((PROJECT_ROOT / "docs" / "llms.txt").read_text(encoding="utf-8"),
                             headers=DOC_HEADERS)


@router.get("/api/docs/examples/{language}", response_class=FileResponse,
            summary="下载 Python 或 Node.js 接入示例", operation_id="downloadIntegrationExample",
            responses={200: {"content": {"text/plain": {"schema": {"type": "string"}}}},
                       404: {"description": "language 只支持 python 或 node"}})
def integration_example(language: str):
    filenames = {"python": "doubao_client.py", "node": "doubao_client.mjs"}
    filename = filenames.get(language)
    if filename is None:
        raise HTTPException(404, "示例不存在；可选 python 或 node")
    return FileResponse(PROJECT_ROOT / "examples" / filename, media_type="text/plain",
                        filename=filename, headers=DOC_HEADERS)
