/**
 * 输入框下方右侧的模型入口：聊天模型配置与本地向量模型切换。
 *
 * 只通过 /model-settings* 接口读写；服务端返回的字符串一律用 textContent 渲染，绝不拼进
 * innerHTML。对外接口：
 *   ModelSettings.init()             挂载入口并读取一次状态
 *   ModelSettings.setStreaming(bool) 本轮生成期间的禁用状态
 *   ModelSettings.canSend()          维护窗口内不可发送/写入
 *   ModelSettings.refreshIfStale()   发送或保存前刷新一次服务端状态
 *   ModelSettings.onBusyChange(fn)   维护状态变化时回调，由页面重新计算按钮禁用状态
 */
const ModelSettings = (() => {
  "use strict";

  const STATUS_MAX_AGE_MS = 5000;
  const POLL_INTERVAL_MS = 1000;
  const STAGE_TEXT = {
    queued: "排队中",
    loading: "加载模型",
    indexing: "建立索引",
    verifying: "校验索引",
    publishing: "发布切换",
    done: "完成",
  };
  const AVAILABILITY_TEXT = {
    available: "可用",
    incomplete: "缓存不完整",
    unsupported: "不支持",
  };
  const PROVIDER_TEXT = {
    deepseek: "DeepSeek",
    "openai-compatible": "OpenAI 兼容",
  };

  const state = {
    revision: 0,
    chat_profiles: [],
    active_chat: null,
    active_embedding: null,
    embedding_candidates: [],
    retrieval_available: true,
    retrieval_problem: null,
    retrieval_state: "ok",
    indexed_files: 0,
    corpus_files: 0,
    busy: false,
    embedding_job: null,
  };
  const dom = {};
  let loadedAt = 0;
  let streaming = false;
  let pollTimer = null;
  let busyListener = null;
  let editingId = null;
  let inFlight = null;

  // ---------- 小工具 ----------

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  function errorText(json, res) {
    if (json && typeof json.message === "string" && json.message) return json.message;
    if (json && typeof json.detail === "string" && json.detail) return json.detail;
    return "HTTP " + res.status;
  }

  function jobRunning() {
    return Boolean(state.embedding_job && state.embedding_job.status === "running");
  }

  // ---------- 状态读取 ----------

  async function fetchStatus(force) {
    if (!force && Date.now() - loadedAt < 1000) return state;
    if (inFlight) return inFlight;
    inFlight = (async () => {
      try {
        const res = await fetch("/model-settings");
        if (!res.ok) return state;
        const json = await res.json();
        applyStatus(json);
      } catch (err) {
        // 状态读不到不影响聊天本身，保持上一次已知状态。
      } finally {
        inFlight = null;
      }
      return state;
    })();
    return inFlight;
  }

  function applyStatus(json) {
    state.revision = json.revision;
    state.chat_profiles = json.chat_profiles || [];
    state.active_chat = json.active_chat || null;
    state.active_embedding = json.active_embedding || null;
    state.retrieval_available = json.retrieval_available !== false;
    state.retrieval_problem = json.retrieval_problem || null;
    state.retrieval_state = json.retrieval_state || "ok";
    state.indexed_files = json.indexed_files || 0;
    state.corpus_files = json.corpus_files || 0;
    state.busy = json.busy === true;
    state.embedding_job = json.embedding_job || null;
    loadedAt = Date.now();
    render();
    notifyBusy();
    if (jobRunning()) startPolling();
    else stopPolling();
  }

  function notifyBusy() {
    if (busyListener) busyListener(state.busy);
    dom.note.hidden = !state.busy;
    if (state.busy) dom.note.textContent = "向量索引重建中：暂时不能发送消息或保存笔记，已有内容仍可查看。";
  }

  async function refreshIfStale() {
    if (Date.now() - loadedAt > STATUS_MAX_AGE_MS) await fetchStatus(true);
    return state;
  }

  // ---------- 渲染 ----------

  function render() {
    const activeChat = state.active_chat;
    dom.chatName.textContent = activeChat ? activeChat.label : "未配置";
    dom.chatName.title = activeChat
      ? `${activeChat.label}（${activeChat.model}）`
      : "尚未配置聊天模型";
    const modelId = state.active_embedding ? state.active_embedding.model_id : "";
    dom.embeddingName.textContent = modelId || "未知";
    dom.embeddingName.title = modelId || "尚未确定向量模型";
    if (dom.chatList) renderChatList();
    if (dom.embeddingList) renderEmbeddings();
  }

  function renderChatList() {
    const list = dom.chatList;
    list.textContent = "";
    if (!state.chat_profiles.length) {
      list.appendChild(el("p", "ms-row-sub", "还没有保存过聊天配置，下面新增一个即可。"));
    }
    state.chat_profiles.forEach((profile) => {
      const isActive = Boolean(state.active_chat && state.active_chat.id === profile.id);
      const row = el("div", "ms-row" + (isActive ? " active" : ""));
      const main = el("div", "ms-row-main");
      main.appendChild(el("div", "ms-row-title", profile.label));
      main.appendChild(
        el("div", "ms-row-sub", `${PROVIDER_TEXT[profile.provider] || profile.provider} · ${profile.model}`)
      );
      const details = [];
      if (profile.credential_source === "env") details.push("凭据来自环境");
      else details.push(profile.has_api_key ? "已保存 Key" : "无需 Key");
      if (profile.base_url) details.push(profile.base_url);
      details.push(`上下文 ${profile.context_window}`);
      main.appendChild(el("div", "ms-row-sub", details.join(" · ")));
      row.appendChild(main);

      if (isActive) {
        row.appendChild(el("span", "ms-chip on", "已启用"));
      } else {
        // 用按钮而不是可点的 span：键盘 Tab + Enter 也能启用。
        const enable = el("button", "ms-chip", "启用");
        enable.type = "button";
        enable.disabled = streaming || jobRunning();
        enable.addEventListener("click", () => activateProfile(profile.id));
        row.appendChild(enable);
      }

      const edit = el("button", "ms-btn", "编辑");
      edit.type = "button";
      edit.disabled = streaming || jobRunning();
      edit.addEventListener("click", () => openForm(profile));
      row.appendChild(edit);

      if (!isActive) {
        // 只有显式删除才会移除配置和它的 Key；当前启用的那条必须先切换走。
        const remove = el("button", "ms-btn", "删除");
        remove.type = "button";
        remove.disabled = streaming || jobRunning();
        remove.addEventListener("click", () => deleteProfile(profile));
        row.appendChild(remove);
      }
      list.appendChild(row);
    });
    if (!state.retrieval_available && state.retrieval_problem) {
      list.appendChild(el("p", "ms-row-sub", state.retrieval_problem));
    }
  }

  function renderEmbeddings() {
    const list = dom.embeddingList;
    list.textContent = "";
    (state.embedding_candidates || []).forEach((candidate) => {
      const row = el("div", "ms-row" + (candidate.active ? " active" : ""));
      const main = el("div", "ms-row-main");
      main.appendChild(el("div", "ms-row-title", candidate.label));
      main.appendChild(el("div", "ms-row-sub", candidate.model_id));
      if (candidate.reason) main.appendChild(el("div", "ms-row-sub", candidate.reason));
      row.appendChild(main);

      if (candidate.active && state.retrieval_available) {
        row.appendChild(el("span", "ms-chip on", "已启用"));
      } else if (candidate.availability === "available") {
        // 当前模型但索引不可用时，同一个按钮就是修复入口。
        const repairing = candidate.active;
        const button = el("button", "ms-btn" + (repairing ? " primary" : ""), repairing ? "重建并修复" : "重建并切换");
        button.type = "button";
        button.disabled = jobRunning() || streaming;
        button.title = "重建期间暂不可发送消息或保存笔记，已有内容仍可查看";
        button.addEventListener("click", () => switchEmbedding(candidate.model_id));
        row.appendChild(button);
        if (repairing) row.appendChild(el("span", "ms-chip warn", "索引不可用"));
      } else {
        const chip = el("span", "ms-chip warn", AVAILABILITY_TEXT[candidate.availability] || "不可用");
        chip.title = candidate.reason || "";
        row.appendChild(chip);
      }
      list.appendChild(row);
    });
    if (!(state.embedding_candidates || []).length) {
      list.appendChild(el("p", "ms-row-sub", "读取中…"));
    }
    // 索引状态写进向量弹层自己的状态区：丢失、指纹不符、空索引各自可辨。
    // 重建进行中时由进度条说明情况，避免和上一轮的状态互相矛盾。
    const retrieval = jobRunning() ? null : retrievalStatus();
    if (retrieval) list.appendChild(el("div", retrieval.className, retrieval.text));
    renderJob();
  }

  function retrievalStatus() {
    switch (state.retrieval_state) {
      case "missing":
        return { className: "ms-error", text: state.retrieval_problem || "索引 collection 不存在，需要重建。" };
      case "config_mismatch":
        return { className: "ms-error", text: state.retrieval_problem || "索引配置已变化，需要重建。" };
      case "unavailable":
        return { className: "ms-error", text: state.retrieval_problem || "向量索引当前不可用。" };
      case "empty":
        if (state.corpus_files > 0) {
          return {
            className: "ms-warn",
            text: `索引里还没有任何片段，但笔记目录有 ${state.corpus_files} 篇：可能需要重建。`,
          };
        }
        return { className: "ms-ok", text: "笔记目录为空，索引为空（状态正常）。" };
      default:
        return {
          className: "ms-row-sub",
          text: `已索引 ${state.indexed_files} 个片段，覆盖 ${state.corpus_files} 篇笔记。`,
        };
    }
  }

  function renderJob() {
    const job = state.embedding_job;
    if (!job) {
      dom.progress.hidden = true;
      return;
    }
    const stage = STAGE_TEXT[job.stage] || job.stage;
    const counter = job.total ? `（${job.completed}/${job.total}）` : "";
    if (job.status === "running") {
      // 上一轮的结果不要留在新任务旁边造成误读。
      dom.embeddingOk.hidden = true;
      dom.embeddingError.hidden = true;
      dom.progress.hidden = false;
      dom.progress.textContent = `正在切换到 ${job.target_model}：${stage}${counter}`;
      dom.barFill.style.width = job.total ? `${Math.round((job.completed / job.total) * 100)}%` : "0%";
      return;
    }
    dom.progress.hidden = true;
    if (job.status === "succeeded") {
      showEmbeddingOk(`已切换到 ${job.target_model}，检索与笔记索引都使用新模型。`);
    } else if (job.status === "interrupted") {
      showEmbeddingError(
        `上次重建被中断（${job.target_model}），仍在使用 ${activeEmbeddingId()}；可以再点一次重试。`
      );
    } else {
      showEmbeddingError(
        `重建失败：${job.error || "未知原因"}。仍在使用 ${activeEmbeddingId()}；可以再点一次重试。`
      );
    }
  }

  function activeEmbeddingId() {
    return state.active_embedding ? state.active_embedding.model_id : "原模型";
  }

  function showError(message) {
    dom.error.textContent = message || "";
    dom.error.hidden = !message;
    if (message) dom.ok.hidden = true;
  }

  function showOk(message) {
    dom.ok.textContent = message || "";
    dom.ok.hidden = !message;
    if (message) dom.error.hidden = true;
  }

  function showEmbeddingError(message) {
    dom.embeddingError.textContent = message || "";
    dom.embeddingError.hidden = !message;
    if (message) dom.embeddingOk.hidden = true;
  }

  function showEmbeddingOk(message) {
    dom.embeddingOk.textContent = message || "";
    dom.embeddingOk.hidden = !message;
    if (message) dom.embeddingError.hidden = true;
  }

  // ---------- 弹层开关 ----------

  function openPopover(kind) {
    closePopover();
    const picker = kind === "chat" ? dom.chatPicker : dom.embeddingPicker;
    const popover = kind === "chat" ? dom.chatPopover : dom.embeddingPopover;
    const trigger = kind === "chat" ? dom.chatTrigger : dom.embeddingTrigger;
    popover.hidden = false;
    trigger.setAttribute("aria-expanded", "true");
    const focusable = popover.querySelector("button, input, select");
    if (focusable) focusable.focus();
    if (kind === "embedding") {
      loadCandidates();
      renderJob();
    } else {
      renderChatList();
    }
    dom.openKind = kind;
  }

  function closePopover() {
    if (!dom.openKind) return;
    const trigger = dom.openKind === "chat" ? dom.chatTrigger : dom.embeddingTrigger;
    dom.chatPopover.hidden = true;
    dom.embeddingPopover.hidden = true;
    dom.chatTrigger.setAttribute("aria-expanded", "false");
    dom.embeddingTrigger.setAttribute("aria-expanded", "false");
    // 焦点回到触发按钮，键盘用户可以继续操作。
    if (trigger) trigger.focus();
    dom.openKind = null;
  }

  // ---------- 聊天配置 ----------

  function openForm(profile) {
    editingId = profile ? profile.id : null;
    const isActive = Boolean(
      profile && state.active_chat && state.active_chat.id === profile.id
    );
    dom.form.hidden = false;
    dom.formTitle.textContent = profile ? `编辑「${profile.label}」` : "新增聊天配置";
    dom.fLabel.value = profile ? profile.label : "";
    dom.fProvider.value = profile ? profile.provider : "deepseek";
    dom.fModel.value = profile ? profile.model : "";
    dom.fBaseUrl.value = profile ? profile.base_url : "";
    // Key 永不回显：留空表示保留已保存的那一个。
    dom.fKey.value = "";
    dom.fKey.placeholder = profile && profile.has_api_key ? "留空保留已保存的 Key" : "";
    dom.fContextWindow.value = profile ? String(profile.context_window) : "32768";
    dom.fAuthNone.checked = profile ? profile.auth_mode === "none" : false;
    dom.fClearKey.checked = false;
    dom.fClearKey.parentElement.hidden = !(profile && profile.has_api_key);
    // 当前启用的配置不能走普通保存：改了文件而运行中的客户端没换，状态就不一致了。
    dom.btnSave.hidden = isActive;
    dom.formActiveNote.hidden = !isActive;
    syncAuthFields();
    showError("");
    showOk("");
    dom.fLabel.focus();
  }

  function closeForm() {
    editingId = null;
    dom.form.hidden = true;
    showError("");
    showOk("");
  }

  function syncAuthFields() {
    dom.fAuthNone.parentElement.hidden = dom.fProvider.value === "deepseek";
    if (dom.fProvider.value === "deepseek") dom.fAuthNone.checked = false;
    if (dom.fClearKey.checked) dom.fKey.value = "";
    dom.fKey.disabled = dom.fAuthNone.checked || dom.fClearKey.checked;
  }

  function formPayload() {
    const payload = {
      label: dom.fLabel.value.trim(),
      provider: dom.fProvider.value,
      model: dom.fModel.value.trim(),
      base_url: dom.fBaseUrl.value.trim(),
      context_window: Number(dom.fContextWindow.value) || 0,
      auth_mode: dom.fAuthNone.checked ? "none" : "api_key",
    };
    if (editingId) payload.id = editingId;
    const key = dom.fKey.value.trim();
    if (key) payload.api_key = key;
    if (dom.fClearKey.checked) payload.clear_api_key = true;
    return payload;
  }

  function setFormBusy(busy) {
    dom.btnTest.disabled = busy;
    dom.btnSave.disabled = busy;
    dom.btnActivate.disabled = busy;
  }

  async function testConnection() {
    setFormBusy(true);
    showError("");
    showOk("");
    try {
      const res = await fetch("/model-settings/chat/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(formPayload()),
      });
      const json = await res.json().catch(() => ({}));
      if (!res.ok) {
        showError(errorText(json, res));
        return;
      }
      const parts = [];
      parts.push(json.streaming ? "流式输出正常" : "流式输出不可用");
      parts.push(json.tool_calling ? "工具调用正常" : "不支持工具调用");
      if (json.message) parts.push(json.message);
      if (json.verified) showOk("连接测试通过：" + parts.join("；"));
      else showError("连接测试未通过：" + parts.join("；"));
    } finally {
      setFormBusy(false);
    }
  }

  async function submitProfile(activate) {
    setFormBusy(true);
    showError("");
    showOk("");
    try {
      await refreshIfStale();
      const body = { ...formPayload(), expected_revision: state.revision };
      let res;
      if (activate) {
        res = await fetch("/model-settings/chat/activate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ expected_revision: state.revision, profile: formPayload() }),
        });
      } else if (editingId) {
        res = await fetch("/model-settings/chat/profiles/" + encodeURIComponent(editingId), {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
      } else {
        res = await fetch("/model-settings/chat/profiles", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
      }
      const json = await res.json().catch(() => ({}));
      if (!res.ok) {
        // 409 说明别的标签页改过配置：刷新后让用户重试，输入不丢。
        showError(errorText(json, res));
        await fetchStatus(true);
        return;
      }
      closeForm();
      await fetchStatus(true);
      showOk(
        activate
          ? `已启用「${json.label}」，下一个问题就会用 ${json.model}。`
          : `已保存「${json.label}」（未启用）。`
      );
    } catch (err) {
      showError((activate ? "启用失败：" : "保存失败：") + err.message);
    } finally {
      setFormBusy(false);
    }
  }

  async function deleteProfile(profile) {
    const confirmed = window.confirm(
      `删除配置「${profile.label}」？该配置保存的 Key 会一并删除，且无法恢复。`
    );
    if (!confirmed) return;
    showError("");
    showOk("");
    try {
      await refreshIfStale();
      const res = await fetch(
        "/model-settings/chat/profiles/" +
          encodeURIComponent(profile.id) +
          "?expected_revision=" +
          state.revision,
        { method: "DELETE" }
      );
      if (!res.ok) {
        const json = await res.json().catch(() => ({}));
        showError(errorText(json, res));
        await fetchStatus(true);
        return;
      }
      await fetchStatus(true);
      showOk(`已删除「${profile.label}」。`);
    } catch (err) {
      showError("删除失败：" + err.message);
    }
  }

  async function activateProfile(profileId) {
    showError("");
    showOk("");
    try {
      await refreshIfStale();
      const res = await fetch("/model-settings/chat/activate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ expected_revision: state.revision, profile_id: profileId }),
      });
      const json = await res.json().catch(() => ({}));
      if (!res.ok) {
        showError(errorText(json, res));
        await fetchStatus(true);
        return;
      }
      await fetchStatus(true);
      showOk(`已启用「${json.label}」。`);
    } catch (err) {
      showError("启用失败：" + err.message);
    }
  }

  // ---------- 向量模型 ----------

  async function loadCandidates() {
    try {
      const res = await fetch("/model-settings/embeddings");
      if (!res.ok) return;
      state.embedding_candidates = await res.json();
      renderEmbeddings();
    } catch (err) {
      // 保持上一次列表；状态区会显示维护提示。
    }
  }

  async function switchEmbedding(modelId) {
    // 向量相关的成败都写进向量弹层自己的状态区，绝不串到聊天弹层。
    showEmbeddingError("");
    showEmbeddingOk("");
    try {
      await refreshIfStale();
      const res = await fetch("/model-settings/embedding/switch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model_id: modelId, expected_revision: state.revision }),
      });
      const json = await res.json().catch(() => ({}));
      if (!res.ok) {
        showEmbeddingError(errorText(json, res));
        await fetchStatus(true);
        return;
      }
      if (json.unchanged) {
        showEmbeddingOk("当前已经在使用这个向量模型，索引也在。");
        await fetchStatus(true);
        return;
      }
      state.embedding_job = json.job;
      // 202 即已进入维护窗口：立刻反映到按钮状态，不等下一次整轮状态刷新。
      state.busy = true;
      notifyBusy();
      renderEmbeddings();
      startPolling();
    } catch (err) {
      showEmbeddingError("切换失败：" + err.message);
    }
  }

  function startPolling() {
    if (pollTimer) return;
    pollTimer = setInterval(pollJob, POLL_INTERVAL_MS);
  }

  function stopPolling() {
    if (!pollTimer) return;
    clearInterval(pollTimer);
    pollTimer = null;
  }

  async function pollJob() {
    // 页面不可见时停掉高频轮询，回到前台再刷新一次。
    if (document.hidden) {
      stopPolling();
      return;
    }
    if (!state.embedding_job) {
      stopPolling();
      return;
    }
    try {
      const res = await fetch("/model-settings/jobs/" + encodeURIComponent(state.embedding_job.id));
      if (!res.ok) return;
      state.embedding_job = await res.json();
    } catch (err) {
      return;
    }
    if (jobRunning()) {
      renderJob();
      return;
    }
    stopPolling();
    await fetchStatus(true);
    await loadCandidates();
  }

  // ---------- 页面接线 ----------

  function buildPopovers() {
    dom.chatPopover = el("div", "model-popover");
    dom.chatPopover.id = "chatModelPopover";
    dom.chatPopover.setAttribute("role", "dialog");
    dom.chatPopover.setAttribute("aria-label", "聊天模型设置");
    dom.chatPopover.hidden = true;
    dom.chatPopover.appendChild(el("h4", null, "聊天模型"));
    dom.chatList = el("div");
    dom.chatPopover.appendChild(dom.chatList);

    const add = el("button", "ms-btn", "＋ 新增配置");
    add.type = "button";
    add.addEventListener("click", () => openForm(null));
    const actions = el("div", "ms-actions");
    actions.appendChild(add);
    dom.chatPopover.appendChild(actions);

    // 表单
    dom.form = el("div");
    dom.form.hidden = true;
    dom.formTitle = el("div", "ms-section-title", "");
    dom.form.appendChild(dom.formTitle);

    dom.fLabel = field(dom.form, "配置名称", "input");
    dom.fProvider = field(dom.form, "provider", "select", [
      ["deepseek", "DeepSeek"],
      ["openai-compatible", "OpenAI 兼容"],
    ]);
    dom.fProvider.addEventListener("change", syncAuthFields);
    dom.fModel = field(dom.form, "模型名", "input");
    dom.fBaseUrl = field(
      dom.form,
      "Base URL",
      "input",
      null,
      "填服务根地址，例如 http://localhost:1234/v1；不要填 /chat/completions"
    );
    dom.fKey = field(dom.form, "API Key", "input");
    dom.fKey.type = "password";
    dom.fKey.autocomplete = "new-password";
    dom.fKey.addEventListener("input", () => {
      // 输入新 Key 与"清除"是互斥意图，服务端也会拒绝同时提交。
      if (dom.fKey.value.trim() && dom.fClearKey.checked) {
        dom.fClearKey.checked = false;
        syncAuthFields();
      }
    });
    const check = el("label", "ms-check");
    dom.fAuthNone = el("input");
    dom.fAuthNone.type = "checkbox";
    dom.fAuthNone.addEventListener("change", syncAuthFields);
    check.appendChild(dom.fAuthNone);
    check.appendChild(el("span", null, "该服务无需 API Key（仅限本地兼容服务）"));
    dom.form.appendChild(check);

    const clear = el("label", "ms-check");
    dom.fClearKey = el("input");
    dom.fClearKey.type = "checkbox";
    dom.fClearKey.addEventListener("change", syncAuthFields);
    clear.appendChild(dom.fClearKey);
    clear.appendChild(el("span", null, "清除已保存的 Key（该配置将不再带凭据）"));
    dom.form.appendChild(clear);
    dom.form.appendChild(
      el(
        "div",
        "ms-hint",
        "留空即保留已保存的 Key；只有勾选「清除」或删除该配置才会移除它。"
      )
    );

    dom.fContextWindow = field(
      dom.form,
      "上下文窗口（token）",
      "input",
      null,
      "用于上下文压缩预算；按服务实际能力填写，不会根据模型名猜测"
    );

    dom.formActiveNote = el(
      "div",
      "ms-hint",
      "这是当前启用的配置：请用「保存并启用」提交，普通保存会改变文件却不更换正在运行的客户端。"
    );
    dom.formActiveNote.hidden = true;
    dom.form.appendChild(dom.formActiveNote);

    dom.formActions = el("div", "ms-actions");
    dom.btnTest = el("button", "ms-btn", "测试连接");
    dom.btnTest.type = "button";
    dom.btnTest.addEventListener("click", testConnection);
    dom.btnSave = el("button", "ms-btn", "保存");
    dom.btnSave.type = "button";
    dom.btnSave.addEventListener("click", () => submitProfile(false));
    dom.btnActivate = el("button", "ms-btn primary", "保存并启用");
    dom.btnActivate.type = "button";
    dom.btnActivate.addEventListener("click", () => submitProfile(true));
    const cancel = el("button", "ms-btn", "取消");
    cancel.type = "button";
    cancel.addEventListener("click", closeForm);
    dom.formActions.appendChild(dom.btnTest);
    dom.formActions.appendChild(dom.btnSave);
    dom.formActions.appendChild(dom.btnActivate);
    dom.formActions.appendChild(cancel);
    dom.form.appendChild(dom.formActions);
    dom.chatPopover.appendChild(dom.form);

    dom.error = el("div", "ms-error");
    dom.error.hidden = true;
    dom.ok = el("div", "ms-ok");
    dom.ok.hidden = true;
    dom.chatPopover.appendChild(dom.error);
    dom.chatPopover.appendChild(dom.ok);
    dom.chatPicker.appendChild(dom.chatPopover);

    // 向量弹层
    dom.embeddingPopover = el("div", "model-popover");
    dom.embeddingPopover.id = "embeddingModelPopover";
    dom.embeddingPopover.setAttribute("role", "dialog");
    dom.embeddingPopover.setAttribute("aria-label", "向量模型设置");
    dom.embeddingPopover.hidden = true;
    dom.embeddingPopover.appendChild(el("h4", null, "向量模型"));
    dom.embeddingPopover.appendChild(
      el("div", "ms-row-sub", "只能选择本地缓存中已存在的受支持模型；本应用不自动下载。")
    );
    dom.embeddingList = el("div");
    dom.embeddingPopover.appendChild(dom.embeddingList);
    dom.progress = el("div", "ms-progress");
    dom.progress.hidden = true;
    dom.bar = el("div", "ms-bar");
    dom.barFill = el("div", "ms-bar-fill");
    dom.bar.appendChild(dom.barFill);
    dom.progress.appendChild(dom.bar);
    dom.embeddingPopover.appendChild(dom.progress);
    dom.embeddingError = el("div", "ms-error");
    dom.embeddingError.hidden = true;
    dom.embeddingPopover.appendChild(dom.embeddingError);
    dom.embeddingOk = el("div", "ms-ok");
    dom.embeddingOk.hidden = true;
    dom.embeddingPopover.appendChild(dom.embeddingOk);
    dom.embeddingPicker.appendChild(dom.embeddingPopover);
  }

  function field(parent, labelText, tag, options, hint) {
    const wrap = el("div", "ms-field");
    const id = "ms-" + Math.random().toString(36).slice(2, 8);
    const label = el("label", null, labelText);
    label.setAttribute("for", id);
    wrap.appendChild(label);
    let input;
    if (tag === "select") {
      input = el("select");
      (options || []).forEach(([value, text]) => {
        const option = el("option", null, text);
        option.value = value;
        input.appendChild(option);
      });
      input.value = (options && options[0] && options[0][0]) || "";
    } else {
      input = el("input");
      input.type = "text";
    }
    input.id = id;
    wrap.appendChild(input);
    if (hint) wrap.appendChild(el("div", "ms-hint", hint));
    parent.appendChild(wrap);
    return input;
  }

  function init() {
    dom.toolbar = document.getElementById("modelToolbar");
    dom.note = document.getElementById("modelToolbarNote");
    dom.chatPicker = document.getElementById("chatPicker");
    dom.embeddingPicker = document.getElementById("embeddingPicker");
    dom.chatTrigger = document.getElementById("btnChatModel");
    dom.embeddingTrigger = document.getElementById("btnEmbeddingModel");
    dom.chatName = document.getElementById("chatModelName");
    dom.embeddingName = document.getElementById("embeddingModelName");
    if (!dom.toolbar) return;

    buildPopovers();

    dom.chatTrigger.addEventListener("click", () => {
      if (dom.openKind === "chat") closePopover();
      else openPopover("chat");
    });
    dom.embeddingTrigger.addEventListener("click", () => {
      if (dom.openKind === "embedding") closePopover();
      else openPopover("embedding");
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && dom.openKind) {
        e.preventDefault();
        closePopover();
      }
    });
    document.addEventListener("click", (e) => {
      if (!dom.openKind) return;
      if (dom.toolbar.contains(e.target)) return;
      closePopover();
    });
    window.addEventListener("focus", () => {
      // 另一个标签页可能刚切换过模型，回到本页时刷新一次。
      fetchStatus(true);
    });
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) {
        stopPolling();
      } else {
        fetchStatus(true);
      }
    });

    fetchStatus(true);
  }

  return {
    init,
    canSend() {
      return !state.busy;
    },
    setStreaming(value) {
      streaming = Boolean(value);
      dom.chatTrigger.disabled = streaming;
      dom.embeddingTrigger.disabled = streaming;
      // 生成中不打断本轮；按钮禁用只是交互层的提示，后端同样保护旧对象。
      if (dom.chatList) renderChatList();
    },
    refreshIfStale,
    onBusyChange(listener) {
      busyListener = listener;
    },
    _state: state,
  };
})();
