import {
  Button,
  Callout,
  Card,
  CardBody,
  CardHeader,
  Code,
  Divider,
  Grid,
  H1,
  H2,
  H3,
  Pill,
  Row,
  Stack,
  Stat,
  Table,
  Text,
  computeDAGLayout,
  useCanvasState,
  useHostTheme,
} from "cursor/canvas";

type ViewId =
  | "overview"
  | "ingest"
  | "quality"
  | "storage"
  | "memory"
  | "retrieval"
  | "implementation"
  | "gap";

const VIEWS: Array<{ id: ViewId; label: string }> = [
  { id: "overview", label: "三层架构" },
  { id: "ingest", label: "摄取流程" },
  { id: "quality", label: "质量与审批" },
  { id: "storage", label: "存储边界" },
  { id: "memory", label: "聊天与记忆" },
  { id: "retrieval", label: "检索服务" },
  { id: "implementation", label: "MVP 实现流程" },
  { id: "gap", label: "与现状差距" },
];

const INGEST_LABELS: Record<string, string> = {
  direct: "直接内容",
  url: "明确 URL",
  search: "纯搜索任务",
  normalize: "规范化输入",
  fetch: "Fetch 指定页",
  researcher: "搜 / 筛 / Fetch",
  bundle: "SourceBundle",
  taxonomy: "分类匹配",
  draft: "NoteDraft",
  quality: "质量门",
  review: "用户审批",
  commit: "正式 Markdown",
  index: "分块与索引",
  api: "Retrieval API",
};

const RETRIEVE_LABELS: Record<string, string> = {
  query: "用户 / 文章 Agent",
  plan: "查询分析",
  local: "本地笔记检索",
  enough: "证据是否充分",
  web: "临时 Web Evidence",
  conflict: "冲突聚类",
  pack: "上下文组装",
  answer: "带引用输出",
};

function FlowChart({
  nodes,
  edges,
  labels,
  accentIds,
  mutedIds,
}: {
  nodes: Array<{ id: string }>;
  edges: Array<{ from: string; to: string }>;
  labels: Record<string, string>;
  accentIds?: string[];
  mutedIds?: string[];
}) {
  const theme = useHostTheme();
  const accentSet = new Set(accentIds ?? []);
  const mutedSet = new Set(mutedIds ?? []);
  const layout = computeDAGLayout({
    nodes,
    edges,
    direction: "vertical",
    nodeWidth: 148,
    nodeHeight: 42,
    rankGap: 52,
    nodeGap: 28,
    padding: 16,
  });
  const byId = new Map(layout.nodes.map((n) => [n.id, n]));

  return (
    <svg
      width="100%"
      viewBox={`0 0 ${layout.width} ${layout.height}`}
      role="img"
      aria-label="architecture flow"
    >
      {layout.ranks.map((rank) => (
        <rect
          key={rank.rank}
          x={rank.x}
          y={rank.y}
          width={rank.width}
          height={rank.height}
          fill={theme.fill.quaternary}
          rx={8}
        />
      ))}
      {layout.edges.map((edge, i) => {
        const midY = (edge.sourceY + edge.targetY) / 2;
        const d = `M ${edge.sourceX} ${edge.sourceY} C ${edge.sourceX} ${midY}, ${edge.targetX} ${midY}, ${edge.targetX} ${edge.targetY}`;
        return (
          <path
            key={`${edge.from}-${edge.to}-${i}`}
            d={d}
            fill="none"
            stroke={
              edge.isBackEdge ? theme.stroke.primary : theme.stroke.secondary
            }
            strokeWidth={1.5}
            strokeDasharray={edge.isBackEdge ? "5 4" : undefined}
            markerEnd="url(#arrow)"
          />
        );
      })}
      <defs>
        <marker
          id="arrow"
          viewBox="0 0 10 10"
          refX="8"
          refY="5"
          markerWidth="7"
          markerHeight="7"
          orient="auto-start-reverse"
        >
          <path d="M 0 0 L 10 5 L 0 10 z" fill={theme.stroke.secondary} />
        </marker>
      </defs>
      {nodes.map((n) => {
        const pos = byId.get(n.id);
        if (!pos) return null;
        const isAccent = accentSet.has(n.id);
        const isMuted = mutedSet.has(n.id);
        return (
          <g key={n.id}>
            <rect
              x={pos.x}
              y={pos.y}
              width={148}
              height={42}
              rx={6}
              fill={
                isAccent
                  ? theme.accent.primary
                  : isMuted
                    ? theme.fill.tertiary
                    : theme.bg.elevated
              }
              stroke={isAccent ? theme.accent.primary : theme.stroke.primary}
            />
            <text
              x={pos.x + 74}
              y={pos.y + 26}
              textAnchor="middle"
              fontSize={12}
              fill={isAccent ? theme.text.onAccent : theme.text.primary}
            >
              {labels[n.id] ?? n.id}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

function Overview() {
  return (
    <Stack gap={16}>
      <Callout tone="info" title="定位">
        NoteAgent 是文章生成工作流中的知识基础设施：生产可审批笔记，再以
        Retrieval API 对外服务。聊天 UI 是验证入口，不是架构中心。
      </Callout>
      <Grid columns={3} gap={12}>
        <Stat value="知识生产" label="采集 / 整理 / 审批" />
        <Stat value="存储与索引" label="Markdown 事实源 + 可重建索引" />
        <Stat value="知识服务" label="统一 Retrieval API" />
      </Grid>
      <H2>三层与模块边界</H2>
      <Grid columns={3} gap={12}>
        <Card>
          <CardHeader trailing={<Pill tone="info">LLM 节点</Pill>}>
            知识生产层
          </CardHeader>
          <CardBody>
            <Stack gap={8}>
              <Text size="small">
                Input Adapter、Source Collector、Search Researcher、Taxonomy、Note
                Composer、Quality Gate、Approval。
              </Text>
              <Text size="small" tone="secondary">
                LLM 只负责分类、筛选、生成草稿和变更理由。写文件、建目录、改索引不由
                Agent 直接执行。
              </Text>
            </Stack>
          </CardBody>
        </Card>
        <Card>
          <CardHeader trailing={<Pill tone="success">确定性</Pill>}>
            存储与索引层
          </CardHeader>
          <CardBody>
            <Stack gap={8}>
              <Text size="small">
                Note Repository、Indexer、Taxonomy Catalog、版本与哈希。
              </Text>
              <Text size="small" tone="secondary">
                正式 Markdown 是事实源。向量库只索引已审批版本，损坏后可从笔记重建。
              </Text>
            </Stack>
          </CardBody>
        </Card>
        <Card>
          <CardHeader trailing={<Pill>契约</Pill>}>知识服务层</CardHeader>
          <CardBody>
            <Stack gap={8}>
              <Text size="small">
                Query Analysis、混合检索、重排去重、相邻 Chunk 展开、引用组装。
              </Text>
              <Text size="small" tone="secondary">
                下游文章 Agent 不接触 Chroma、Embedding 或文件目录，只消费
                RetrievalResult。
              </Text>
            </Stack>
          </CardBody>
        </Card>
      </Grid>
      <H2>架构原则</H2>
      <Table
        headers={["原则", "含义"]}
        rows={[
          [
            "Workflow-first",
            "状态机固定阶段；LLM 只在局部节点工作，不主导全流程",
          ],
          [
            "Curated knowledge first",
            "先保证知识可信，再优化检索，最后才优化聊天体验",
          ],
          [
            "摄取与问答解耦",
            "写笔记失败不污染索引；索引失败不回滚已批准笔记",
          ],
          [
            "LLM 提案、代码执行",
            "输出 KnowledgeChangeSet，由 Executor 原子写入",
          ],
          [
            "source-only",
            "整理只依据选定来源；推论必须标明；冲突并列呈现",
          ],
        ]}
        striped
      />
    </Stack>
  );
}

function Ingest() {
  return (
    <Stack gap={16}>
      <Text tone="secondary">
        三条入口只在材料获取阶段不同，进入 SourceBundle 后走同一条知识提交管线。虚线表示审批退回重写。橙色节点是唯一主要
        Human-in-the-loop 点。
      </Text>
      <FlowChart
        nodes={[
          { id: "direct" },
          { id: "url" },
          { id: "search" },
          { id: "normalize" },
          { id: "fetch" },
          { id: "researcher" },
          { id: "bundle" },
          { id: "taxonomy" },
          { id: "draft" },
          { id: "quality" },
          { id: "review" },
          { id: "commit" },
          { id: "index" },
          { id: "api" },
        ]}
        edges={[
          { from: "direct", to: "normalize" },
          { from: "url", to: "fetch" },
          { from: "search", to: "researcher" },
          { from: "normalize", to: "bundle" },
          { from: "fetch", to: "bundle" },
          { from: "researcher", to: "bundle" },
          { from: "bundle", to: "taxonomy" },
          { from: "taxonomy", to: "draft" },
          { from: "draft", to: "quality" },
          { from: "quality", to: "review" },
          { from: "review", to: "draft" },
          { from: "review", to: "commit" },
          { from: "commit", to: "index" },
          { from: "index", to: "api" },
        ]}
        labels={INGEST_LABELS}
        accentIds={["review"]}
        mutedIds={["direct", "url", "search"]}
      />
      <H2>入口差异</H2>
      <Table
        headers={["入口", "系统做什么", "笔记形态"]}
        rows={[
          [
            "直接内容",
            "规范化所选聊天消息，不联网",
            "单来源笔记，source_type=conversation",
          ],
          [
            "明确 URL",
            "Fetch 该页；不替用户另选来源",
            "一篇 Blog 对应一篇 Markdown",
          ],
          [
            "纯搜索",
            "规划查询、质量筛选、Fetch 入选页、交叉验证",
            "一篇多来源综合笔记，观点带 [S1] 引用",
          ],
        ]}
        striped
      />
      <H3>状态机</H3>
      <Text>
        SUBMITTED → FETCHED → CLASSIFIED → DRAFTED → PENDING_REVIEW → APPROVED →
        COMMITTED → INDEX_PENDING → INDEXED。失败单独记录，从对应阶段重试，不整条重跑。
      </Text>
      <Callout tone="warning" title="网页正文生命周期">
        不长期保存全文。临时正文至少保留到生成、独立 Reviewer、用户审批、正式写入成功之后再丢弃。长期只留
        URL、标题、作者、fetched_at、source_content_hash 和笔记中的必要引用。
      </Callout>
    </Stack>
  );
}

function Quality() {
  return (
    <Stack gap={16}>
      <H2>审批对象：KnowledgeChangeSet</H2>
      <Text>
        一次输入可能同时涉及新分类、新笔记、路径和 metadata。用户在同一 ChangeSet
        里看 Diff，批量批准或逐项修改。LLM 不直接 mkdir / 写文件。
      </Text>
      <Grid columns={2} gap={12}>
        <Card>
          <CardHeader>必须审批</CardHeader>
          <CardBody>
            <Text size="small">
              新建分类目录、新建正式笔记、大幅重写、合并/移动/删除、来源冲突、低置信度分类、来源无法支撑的新结论。纯搜索还要展示采用来源，并折叠排除来源及原因。
            </Text>
          </CardBody>
        </Card>
        <Card>
          <CardHeader>自动执行</CardHeader>
          <CardBody>
            <Text size="small">
              Fetch、清洗、元数据抽取、确定性校验、已批准文档的分块 / Embedding /
              索引、索引失败后的安全重试。索引失败不回滚已批准笔记。
            </Text>
          </CardBody>
        </Card>
      </Grid>
      <H2>三层质量门</H2>
      <Table
        headers={["层", "谁执行", "阻断条件"]}
        rowTone={["danger", "warning", "info"]}
        rows={[
          [
            "确定性校验",
            "程序",
            "缺 metadata、非法路径、引用对不上、高度重复 → 不进审批",
          ],
          [
            "独立 Reviewer",
            "与生成分离的 LLM",
            "无来源支撑的事实、漏核心结论、缺 URL → 不通过",
          ],
          [
            "用户审批",
            "Human",
            "值不值得入库、分类是否符合个人体系、冲突如何表达",
          ],
        ]}
      />
      <H2>笔记 Schema</H2>
      <Text>
        统一 metadata 外壳 + 按类型选正文模板。稳定核心章节：概览、核心观点、详细内容、适用范围与局限、来源。教程 / 概念 / 观点 / 研究综合另加可选章节。
      </Text>
      <Text size="small" tone="secondary">
        Identity 用稳定 note_id；Provenance 用来源数组；Classification 用
        category_id + tags。目录路径可变，不能当唯一身份。
      </Text>
      <Callout title="分类治理">
        优先匹配已有主题；同主题优先更新已有笔记；找不到笔记才提议新建
        Markdown；找不到主题才提议新建文件夹。新分类必须带 parent、范围、近义校验，由执行器创建并写入
        Taxonomy Catalog。
      </Callout>
    </Stack>
  );
}

function Storage() {
  return (
    <Stack gap={16}>
      <H2>四个逻辑存储域</H2>
      <Grid columns={2} gap={12}>
        <Card>
          <CardHeader trailing={<Pill>产品数据</Pill>}>会话存储</CardHeader>
          <CardBody>
            <Text size="small">
              conversation、message、LLM run、tool call、草稿关联。用于恢复聊天，不进入
              RAG。
            </Text>
          </CardBody>
        </Card>
        <Card>
          <CardHeader trailing={<Pill tone="warning">可暂停</Pill>}>
            工作流与审计
          </CardHeader>
          <CardBody>
            <Text size="small">
              ingestion 状态、ChangeSet、审批决定、模型/Prompt 版本、错误与重试。应用重启后仍能继续审批。
            </Text>
          </CardBody>
        </Card>
        <Card>
          <CardHeader trailing={<Pill tone="success">事实源</Pill>}>
            正式知识库
          </CardHeader>
          <CardBody>
            <Text size="small">
              审批后的 Markdown、frontmatter、笔记版本、分类目录。人类可读、可迁移。
            </Text>
          </CardBody>
        </Card>
        <Card>
          <CardHeader trailing={<Pill tone="info">可重建</Pill>}>
            向量索引
          </CardHeader>
          <CardBody>
            <Text size="small">
              由正式 Markdown 派生。只索引 APPROVED/COMMITTED。Chunk 继承
              note_id、version、heading_path、content_hash。
            </Text>
          </CardBody>
        </Card>
      </Grid>
      <H2>身份与幂等</H2>
      <Table
        headers={["ID", "作用"]}
        rows={[
          ["ingestion_id", "一次摄取任务，贯穿日志与审批"],
          ["note_id", "笔记稳定身份，移动文件不改变"],
          ["note_version", "正式内容变更递增，防止旧 Chunk 残留"],
          ["category_id", "分类稳定身份，路径只是物理位置"],
          ["source_content_hash", "判断同一 URL 内容是否变化，不存正文"],
          ["chunk_id + chunk_hash", "增量 upsert / delete，重复跑不污染"],
        ]}
        striped
      />
      <H3>存储承载</H3>
      <Text>
        PostgreSQL 存聊天、工作流、审批、分类目录、偏好和审计；Markdown 存正式知识；Chroma 作派生向量索引。LangGraph
        使用 PostgresSaver 做 checkpoint，但 Job.status 仍以业务表为准。
      </Text>
    </Stack>
  );
}

const CONTEXT_LABELS: Record<string, string> = {
  store: "完整会话库",
  summary: "滚动摘要",
  recent: "最近消息",
  prefs: "用户偏好",
  task: "当前任务工作区",
  window: "本轮 LLM 上下文",
};

function Memory() {
  return (
    <Stack gap={16}>
      <Callout tone="warning" title="现状问题">
        当前用 LangGraph InMemorySaver + thread_id 当聊天历史；退出时把摘要写入
        notes/context.md。这会把运行状态、聊天记忆和正式知识混在同一个文件里，重启即丢会话，摘要还可能被索引。
      </Callout>
      <Callout tone="info" title="已确认">
        形态是普通对话 Agent，主能力是笔记整理。会话可切换、长期保留；Agent
        工作（搜索、草稿、审批）嵌在该会话时间线里。长期记忆是用户可查看、可修改的偏好档案，由
        LLM 逐步提炼，不是把聊天摘要写进知识库。
      </Callout>
      <Grid columns={4} gap={12}>
        <Stat value="聊天历史" label="完整消息，恢复会话" />
        <Stat value="运行上下文" label="本轮发给模型的窗口" />
        <Stat value="用户偏好" label="可见可改的长期记忆" />
        <Stat value="正式知识" label="已审批笔记 + RAG" />
      </Grid>
      <H2>数据关系</H2>
      <Text>
        Conversation 1 — N Message，并可派生 0 — N 个 IngestionJob（建议同一时刻只跑一个活跃任务）。时间线同时展示对话气泡和任务状态卡片；审批详情挂在
        Job 上，不把 ChangeSet 整段塞进一条 assistant 文本。
      </Text>
      <H2>本轮上下文如何组装</H2>
      <FlowChart
        nodes={[
          { id: "store" },
          { id: "summary" },
          { id: "recent" },
          { id: "prefs" },
          { id: "task" },
          { id: "window" },
        ]}
        edges={[
          { from: "store", to: "summary" },
          { from: "store", to: "recent" },
          { from: "prefs", to: "window" },
          { from: "summary", to: "window" },
          { from: "recent", to: "window" },
          { from: "task", to: "window" },
        ]}
        labels={CONTEXT_LABELS}
        accentIds={["window"]}
        mutedIds={["store"]}
      />
      <Table
        headers={["层", "进 LLM？", "进 RAG？"]}
        rows={[
          ["完整聊天记录", "否，只作恢复与审计", "否"],
          ["滚动摘要 + 最近 N 条", "是", "否"],
          ["当前 SourceBundle / 草稿指针", "是，且有 token 预算", "否"],
          ["工具完整轨迹", "默认否，需要时再注入摘要", "否"],
          ["已审批笔记", "仅问答轮次经 Retrieval API", "是"],
        ]}
        striped
      />
      <H3>LangGraph checkpoint 的位置</H3>
      <Text>
        Checkpointer 只保存进行中的图执行（可中断审批、失败重试）。它不是聊天数据库，也不能替代
        Conversation / Message 表。用户可见历史从业务库读，不从 checkpoint 反序列化。
      </Text>
      <H2>偏好档案（长期记忆）</H2>
      <Text>
        这是一份有上限的结构化 Profile，不是越聊越长的记忆全文。字段级覆盖写入（例如「正文用到三级标题」），不追加流水账。仅在重复出现或信号足够强时更新，并带冷却；设置页可改。不写进正式笔记，也不参与
        source-only 正文。
      </Text>
      <Table
        headers={["字段类", "例子"]}
        rows={[
          ["结构偏好", "是否使用三级标题、章节密度、先摘要后细节"],
          ["分类偏好", "常用主题路径、标签粒度、何时新建目录"],
          ["文风偏好", "中文、信息密度、少套话"],
          ["工作流偏好", "搜索时来源数量、审批时默认展开排除来源"],
        ]}
        striped
      />
    </Stack>
  );
}

function Retrieval() {
  return (
    <Stack gap={16}>
      <Text tone="secondary">
        直接问答与文章 Agent 共用 Retrieval API。实时网页不得与已审核知识混称为同一类结果。
      </Text>
      <FlowChart
        nodes={[
          { id: "query" },
          { id: "plan" },
          { id: "local" },
          { id: "enough" },
          { id: "web" },
          { id: "conflict" },
          { id: "pack" },
          { id: "answer" },
        ]}
        edges={[
          { from: "query", to: "plan" },
          { from: "plan", to: "local" },
          { from: "local", to: "enough" },
          { from: "enough", to: "conflict" },
          { from: "enough", to: "web" },
          { from: "web", to: "conflict" },
          { from: "conflict", to: "pack" },
          { from: "pack", to: "answer" },
        ]}
        labels={RETRIEVE_LABELS}
        accentIds={["enough"]}
        mutedIds={["web"]}
      />
      <H2>本地优先路由</H2>
      <Table
        headers={["情况", "策略"]}
        rows={[
          ["非时效且本地充分", "只用本地笔记"],
          ["本地不足", "补充临时 Web Evidence，并标记未审核"],
          ["明显时效问题", "本地与 Web 同时检索"],
          ["Web 与本地冲突", "不覆盖本地笔记；披露双方；可生成维护任务"],
          ["一次问答用到网页", "不自动入库；有长期价值再走摄取审批"],
        ]}
        striped
      />
      <H2>RetrievalResult 契约</H2>
      <Text>
        content、note_id、note_version、title、category_id、topic_path、tags、file_path、heading_path、source_urls、score、citation。
        另支持 metadata 过滤、相邻 Chunk 展开、每篇笔记召回上限、证据不足标记。
      </Text>
      <Callout tone="warning" title="冲突不能只比新">
        新内容不一定更正确，向量相似度不是事实置信度。先判断是否时间 / 版本 /
        适用条件不同；无法判定则并列引用，降低答案置信度。
      </Callout>
    </Stack>
  );
}

function Gap() {
  return (
    <Stack gap={16}>
      <Callout tone="neutral" title="当前实现">
        聊天驱动的 Markdown 笔记 MVP：能聊、能写 notes/*.md、能检索。入库需手动触发，Agent
        可直接写文件。
      </Callout>
      <Table
        headers={["目标能力", "现状", "缺口"]}
        rowTone={[
          "danger",
          "danger",
          "warning",
          "warning",
          "info",
          "info",
          "neutral",
        ]}
        rows={[
          ["ChangeSet + 审批", "Agent 直接写文件", "缺校验边界与 HITL"],
          ["自动增量索引", "手动 RAG 入库", "文件与 Chroma 不一致"],
          ["URL / Search", "仅聊天文本", "无 Fetch、筛选、来源质量"],
          ["稳定 metadata / 版本", "Prompt 约束结构", "无 note_id、哈希、分类 ID"],
          ["工作流持久化", "内存会话", "关闭页面后无法恢复审批"],
          ["Retrieval API", "Agent 工具返回纯文本", "无引用、章节、版本"],
          ["审计与质量指标", "部分运行日志", "缺知识审计与用户改稿数据"],
        ]}
      />
      <H2>记忆必须拆开</H2>
      <Grid columns={4} gap={12}>
        <Stat value="聊天历史" label="恢复会话，未经审批不入库" />
        <Stat value="运行上下文" label="发给模型的窗口，需裁剪" />
        <Stat value="用户偏好" label="分类习惯、常用标签" />
        <Stat value="正式知识" label="已审批 Markdown + 索引" />
      </Grid>
    </Stack>
  );
}

function Implementation() {
  return (
    <Stack gap={16}>
      <Callout tone="info" title="AI 实现边界">
        保留现有 FastAPI、聊天页和 Chroma，改造成模块化单体。LangGraph 编排可暂停节点；PostgreSQL
        保存业务事实；Markdown 是正式知识源；Chroma 是可重建索引。不要让 AI 一次重写整个项目。
      </Callout>
      <H2>建议按依赖顺序实现</H2>
      <Table
        headers={["阶段", "AI 要实现的产物", "验收条件"]}
        rows={[
          [
            "1. 数据基础",
            "PostgreSQL + SQLAlchemy/Alembic：Conversation、Message、IngestionJob、Approval、NoteVersion",
            "重启后会话、消息和待审批任务仍存在",
          ],
          [
            "2. 聊天持久化",
            "会话 CRUD、消息落库、SSE 完成/失败状态；移除退出时写 context.md",
            "可切换历史会话；普通聊天不进入 RAG",
          ],
          [
            "3. 任务骨架",
            "SourceBundle、NoteDraft、KnowledgeChangeSet 数据契约；Job 状态与合法转移",
            "URL/文本都能创建任务并暂停在 PENDING_REVIEW",
          ],
          [
            "4. LangGraph 编排",
            "Fetch/分类/生成/校验/interrupt 审批/提交节点与持久化 checkpoint",
            "关闭应用后可恢复；节点失败只重试该节点",
          ],
          [
            "5. 审批提交",
            "草稿、分类、metadata、来源和 Diff 页面；批准/修改/拒绝接口",
            "只有批准操作能由 Executor 原子写 Markdown",
          ],
          [
            "6. 自动索引",
            "Markdown 二三级标题切分；长拆短并；BGE-small-zh-v1.5；增量 upsert/delete",
            "写入后自动索引；重复执行不产生重复 Chunk",
          ],
          [
            "7. MVP 检索",
            "向量 Top-K、阈值、每笔记上限、相邻 Chunk、token 预算、引用",
            "无可靠证据时返回 insufficient_evidence",
          ],
          [
            "8. 质量闭环",
            "10–20 条人工查询集；记录命中、漏检、用户改稿与拒绝原因",
            "用失败样本调整阈值和 Chunk，不凭感觉改参数",
          ],
        ]}
        rowTone={["info", "info", "warning", "warning", "success", "success", "neutral", "neutral"]}
        striped
      />
      <H2>端到端运行路径</H2>
      <Text>
        用户消息先落库 → Agent 判断普通对话或笔记任务 → 创建 Job → 获取 SourceBundle → 分类和生成草稿
        → 程序校验 + 独立 Reviewer → interrupt 等待用户 → Executor 写正式 Markdown → 创建索引任务
        → 章节感知 Chunk → 中文 Embedding → Chroma upsert → Retrieval API 可查询。
      </Text>
      <H2>AI 编码时必须遵守</H2>
      <Grid columns={2} gap={12}>
        <Card>
          <CardHeader>职责边界</CardHeader>
          <CardBody>
            <Text size="small">
              LLM 只能返回结构化提案；分类目录、Markdown、版本和索引由确定性 Service/Repository
              执行。API 不直接操作向量库内部结构。
            </Text>
          </CardBody>
        </Card>
        <Card>
          <CardHeader>幂等与一致性</CardHeader>
          <CardBody>
            <Text size="small">
              所有副作用带 ingestion_id、note_id、note_version、content_hash。Markdown 已提交但索引失败时只重试索引，不能重新审批。
            </Text>
          </CardBody>
        </Card>
        <Card>
          <CardHeader>安全与来源</CardHeader>
          <CardBody>
            <Text size="small">
              网页是数据而不是指令；Collector 无写文件权限。笔记 source-only；英文来源直接生成中文笔记，并由 Reviewer
              对照原文。
            </Text>
          </CardBody>
        </Card>
        <Card>
          <CardHeader>版本与可替换性</CardHeader>
          <CardBody>
            <Text size="small">
              记录 prompt、模型、Schema、Chunk、Embedding 版本。检索接口与 Chroma
              解耦，为后续混合检索 + rerank 保留替换点。
            </Text>
          </CardBody>
        </Card>
      </Grid>
      <Callout tone="warning" title="MVP 不做">
        不做多用户、微服务、专用翻译模型、混合检索、rerank、自动知识合并、复杂长期记忆。先保证会话持久化、审批、自动索引和带引用向量检索闭环。
      </Callout>
    </Stack>
  );
}

export default function NoteAgentArchitecture() {
  const [view, setView] = useCanvasState<ViewId>("view", "overview");

  return (
    <Stack gap={20} style={{ padding: 8 }}>
      <Stack gap={8}>
        <H1>NoteAgent 架构基线</H1>
        <Text tone="secondary">
          上次讨论冻结的 v1：确定性知识工作流 + 人工审批正式知识 + 可重建 RAG。业务库已定为 PostgreSQL；向量库继续用 Chroma。
        </Text>
      </Stack>
      <Row gap={8} wrap>
        {VIEWS.map((item) => (
          <span key={item.id}>
            <Button
              variant={view === item.id ? "primary" : "secondary"}
              onClick={() => setView(item.id)}
            >
              {item.label}
            </Button>
          </span>
        ))}
      </Row>
      <Divider />
      {view === "overview" ? <Overview /> : null}
      {view === "ingest" ? <Ingest /> : null}
      {view === "quality" ? <Quality /> : null}
      {view === "storage" ? <Storage /> : null}
      {view === "memory" ? <Memory /> : null}
      {view === "retrieval" ? <Retrieval /> : null}
      {view === "implementation" ? <Implementation /> : null}
      {view === "gap" ? <Gap /> : null}
      <Divider />
      <Text size="small" tone="tertiary">
        来源：NoteAgent 架构讨论基线 · 2026-08-17。图中 <Code>SourceBundle</Code>{" "}
        之后为统一管线；检索中的 Web 节点为临时证据，不是正式知识。
      </Text>
    </Stack>
  );
}
