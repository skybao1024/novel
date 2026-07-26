# Narrative Core JSON Schemas

本目录保存 Narrative Core 当前公共领域契约的 JSON Schema。

Schema 由 Pydantic 模型确定性生成，不手工编辑。在 `backend/` 中运行：

```text
python scripts/generate_schemas.py
python scripts/generate_schemas.py --check
```

每份 Schema 包含顶层 `x-schema-version`，并与模型 JSON 中的 `schema_version` 一致。
目录只保存正式业务契约对应的生成文件。
