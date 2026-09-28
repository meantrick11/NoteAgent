import {
  Callout,
  H1,
  H2,
  Pill,
  Row,
  Stack,
  Text,
  useHostTheme,
} from "cursor/canvas";

type Node = {
  id: string;
  label: string;
  sub?: string;
  x: number;
  y: number;
  w?: number;
  tone?: "normal" | "accent" | "muted" | "warning" | "success";
};

type Edge = {
  from: string;
  to: string;
  label?: string;
  dashed?: boolean;
};

const nodes: Node[] = [
  { id: "chat", label: "对话文本", x: 70, y: 70, tone: "muted" },
  { id: "url", label: "明确 URL", x: 280, y: 70, tone: "muted" },
  { id: "search", label: "搜索主题", x: 490, y: 70, tone: "muted" },
  { id: "article", label: "文章 Agent", sub: "下游调用方", x: 1120, y: 70, tone: "muted" },

  { id: "api", label: "Chat / Task API", sub: "消息先落库", x: 280, y: 180, w: 220 },
  { id: "router", label: "Agent Router", sub: "对话 or 知识任务", x: 280, y: 280, w: 220, tone: "accent" },
  { id: "dialogue", label: "普通对话", sub: "摘要 + 近轮 + 偏好", x: 70, y: 390, w: 220 },
  { id: "source", label: "Source Adapter", sub: "Direct / Fetch / Search", x: 390, y: 390, w: 240 },
  { id: "bundle", label: "SourceBundle", sub: "统一临时材料", x: 390, y: 490, w: 240 },
  { id: "taxonomy", label: "分类匹配", sub: "已有分类 / 新分类提案", x: 390, y: 590, w: 240 },
  { id: "compose", label: "Note Composer", sub: "source-only 中文草稿", x: 390, y: 690, w: 240 },
  { id: "validate", label: "质量门", sub: "规则校验 + 独立 Reviewer", x: 390, y: 790, w: 240 },
  { id: "review", label: "用户审批", sub: "内容 / 分类 / 来源 / Diff", x: 390, y: 900, w: 240, tone: "warning" },
  { id: "executor", label: "Executor", sub: "原子写入 + 版本", x: 720, y: 900, w: 220, tone: "success" },
  { id: "markdown", label: "正式 Markdown", sub: "唯一知识事实源", x: 1020, y: 900, w: 240, tone: "success" },

  { id: "indexjob", label: "Index Job", sub: "失败可独立重试", x: 1020, y: 790, w: 240 },
  { id: "chunk", label: "章节感知 Chunk", sub: "H2/H3；长拆短并", x: 1020, y: 690, w: 240 },
  { id: "embed", label: "中文 Embedding", sub: "BGE-small-zh-v1.5", x: 1020, y: 590, w: 240 },
  { id: "chroma", label: "Chroma", sub: "可重建向量索引", x: 1020, y: 490, w: 240, tone: "muted" },

  { id: "retrieval", label: "Retrieval API", sub: "统一检索契约", x: 1020, y: 280, w: 240, tone: "accent" },
  { id: "control", label: "召回控制", sub: "Top-K / 阈值 / 去重 / 邻居", x: 1020, y: 390, w: 240 },
  { id: "evidence", label: "Evidence Pack", sub: "章节、来源、引用、置信度", x: 720, y: 390, w: 220 },
  { id: "answer", label: "Answer LLM", sub: "中文带引用生成", x: 720, y: 280, w: 220 },
  { id: "output", label: "SSE 输出", sub: "回答 / 任务状态", x: 70, y: 280, w: 180, tone: "success" },

  { id: "postgres", label: "PostgreSQL", sub: "会话 / 消息 / Job / 审批", x: 70, y: 580, w: 240, tone: "muted" },
  { id: "checkpoint", label: "LangGraph Checkpoint", sub: "interrupt / resume / retry", x: 70, y: 690, w: 240, tone: "muted" },
  { id: "audit", label: "Audit / Trace", sub: "状态 / 模型 / Prompt / 错误", x: 70, y: 800, w: 240, tone: "muted" },
];

const edges: Edge[] = [
  { from: "chat", to: "api" },
  { from: "url", to: "api" },
  { from: "search", to: "api" },
  { from: "api", to: "router" },
  { from: "router", to: "dialogue", label: "普通聊天" },
  { from: "dialogue", to: "output" },
  { from: "router", to: "source", label: "整理笔记" },
  { from: "source", to: "bundle" },
  { from: "bundle", to: "taxonomy" },
  { from: "taxonomy", to: "compose" },
  { from: "compose", to: "validate" },
  { from: "validate", to: "review" },
  { from: "review", to: "compose", label: "修改 / 退回", dashed: true },
  { from: "review", to: "executor", label: "批准" },
  { from: "executor", to: "markdown" },
  { from: "markdown", to: "indexjob" },
  { from: "indexjob", to: "chunk" },
  { from: "chunk", to: "embed" },
  { from: "embed", to: "chroma" },
  { from: "article", to: "retrieval" },
  { from: "router", to: "retrieval", label: "知识问答" },
  { from: "retrieval", to: "control" },
  { from: "control", to: "chroma" },
  { from: "control", to: "evidence" },
  { from: "evidence", to: "answer" },
  { from: "answer", to: "output" },
  { from: "api", to: "postgres", dashed: true },
  { from: "router", to: "checkpoint", dashed: true },
  { from: "source", to: "audit", dashed: true },
  { from: "review", to: "postgres", dashed: true },
];

function SystemFlow() {
  const theme = useHostTheme();
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const fillFor = (tone: Node["tone"]) => {
    if (tone === "accent") return theme.accent.primary;
    if (tone === "muted") return theme.fill.tertiary;
    if (tone === "warning") return theme.fill.secondary;
    if (tone === "success") return theme.fill.primary;
    return theme.bg.elevated;
  };
  const textFor = (tone: Node["tone"]) =>
    tone === "accent" ? theme.text.onAccent : theme.text.primary;

  return (
    <svg
      viewBox="0 0 1360 1010"
      width="100%"
      role="img"
      aria-label="NoteAgent 整体系统工作流程图"
    >
      <rect x="35" y="35" width="1290" height="110" rx="10" fill={theme.fill.quaternary} />
      <text x="50" y="58" fontSize="12" fill={theme.text.tertiary}>输入与消费者</text>
      <rect x="35" y="155" width="1290" height="275" rx="10" fill={theme.fill.quaternary} />
      <text x="50" y="178" fontSize="12" fill={theme.text.tertiary}>应用与知识服务</text>
      <rect x="35" y="445" width="1290" height="520" rx="10" fill={theme.fill.quaternary} />
      <text x="50" y="468" fontSize="12" fill={theme.text.tertiary}>知识生产、持久化与索引</text>

      <defs>
        <marker id="workflow-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto">
          <path d="M 0 0 L 10 5 L 0 10 z" fill={theme.stroke.secondary} />
        </marker>
      </defs>

      {edges.map((edge, index) => {
        const from = byId.get(edge.from);
        const to = byId.get(edge.to);
        if (!from || !to) return null;
        const fw = from.w ?? 180;
        const tw = to.w ?? 180;
        const startX = from.x + fw / 2;
        const startY = from.y + 58;
        const endX = to.x + tw / 2;
        const endY = to.y;
        const isUp = endY < startY;
        const midY = isUp ? Math.min(startY - 36, endY + 36) : (startY + endY) / 2;
        const d = `M ${startX} ${startY} C ${startX} ${midY}, ${endX} ${midY}, ${endX} ${endY}`;
        return (
          <g key={`${edge.from}-${edge.to}-${index}`}>
            <path
              d={d}
              fill="none"
              stroke={theme.stroke.secondary}
              strokeWidth={1.4}
              strokeDasharray={edge.dashed ? "5 4" : undefined}
              markerEnd="url(#workflow-arrow)"
            />
            {edge.label ? (
              <text
                x={(startX + endX) / 2 + 5}
                y={midY - 5}
                fontSize="10"
                fill={theme.text.tertiary}
              >
                {edge.label}
              </text>
            ) : null}
          </g>
        );
      })}

      {nodes.map((node) => {
        const width = node.w ?? 180;
        return (
          <g key={node.id}>
            <rect
              x={node.x}
              y={node.y}
              width={width}
              height={58}
              rx="7"
              fill={fillFor(node.tone)}
              stroke={node.tone === "accent" ? theme.accent.primary : theme.stroke.primary}
            />
            <text
              x={node.x + width / 2}
              y={node.y + (node.sub ? 24 : 34)}
              textAnchor="middle"
              fontSize="13"
              fontWeight="600"
              fill={textFor(node.tone)}
            >
              {node.label}
            </text>
            {node.sub ? (
              <text
                x={node.x + width / 2}
                y={node.y + 43}
                textAnchor="middle"
                fontSize="10"
                fill={node.tone === "accent" ? theme.text.onAccent : theme.text.secondary}
              >
                {node.sub}
              </text>
            ) : null}
          </g>
        );
      })}
    </svg>
  );
}

export default function NoteAgentSystemWorkflow() {
  return (
    <Stack gap={16} style={{ padding: 8 }}>
      <Stack gap={6}>
        <H1>NoteAgent 整体系统工作流程</H1>
        <Text tone="secondary">
          普通聊天、笔记生产、人工审批、自动索引和 RAG 检索共享一个模块化单体；虚线表示持久化、审计或回退关系。
        </Text>
      </Stack>
      <Row gap={8} wrap>
        <Pill tone="info">蓝色：路由与服务入口</Pill>
        <Pill tone="warning">审批：Human in the loop</Pill>
        <Pill tone="success">绿色：正式产物</Pill>
        <Pill>灰色：存储与外部入口</Pill>
      </Row>
      <SystemFlow />
      <H2>关键规则</H2>
      <Callout tone="warning" title="可信边界">
        LLM 只生成分类、草稿和变更提案；用户批准后，Executor 才能写正式 Markdown。向量库只索引已批准版本。
      </Callout>
      <Callout tone="info" title="恢复与一致性">
        PostgreSQL 保存会话和业务状态；LangGraph PostgresSaver 负责 interrupt/resume。Markdown 已提交但索引失败时，只重试 Index Job，不回滚笔记。
      </Callout>
      <Text size="small" tone="tertiary">
        MVP：中文笔记、BGE-small-zh-v1.5、Chroma 纯向量检索。后期可在 Retrieval API 内增加关键词召回与 rerank，不改变上层契约。
      </Text>
    </Stack>
  );
}
