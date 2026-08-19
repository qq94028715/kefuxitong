<template>
  <div>
    <div class="topbar">
      <div class="brand">客服训练系统 · 训练端</div>
      <div class="actions">
        <span>{{ username }}</span>
        <button class="btn ghost sm" @click="logout">退出</button>
      </div>
    </div>

    <div class="container">
      <div class="card">
        <!-- 入口：开新批 / 继续练 / 等待判定 -->
        <div v-if="!chatting">
          <div class="page-title-row">
            <div>
              <div class="page-title">错题本训练</div>
              <div class="page-sub">每批 20 道客户情景题，AI 客户按真实聊天记录扮演。错题会间隔混入后续批次，直到主管判定合格。</div>
            </div>
            <button class="btn ghost sm" @click="router.push('/mastery')">查看掌握度</button>
          </div>

          <!-- 批次状态条 -->
          <div v-if="progress.has_batch" class="batch-status">
            <div class="batch-status-row">
              <span class="tag" :class="batchStatusClass(progress.batch.status)">
                {{ batchStatusLabel(progress.batch.status) }}
              </span>
              <span class="muted">{{ progress.batch.category_name }}</span>
              <span class="muted" style="margin-left:auto">
                已完成 {{ progress.done_count }}/{{ progress.batch.question_count }} 题
              </span>
            </div>
            <div class="muted" style="margin-top:6px">
              <template v-if="progress.mistake_count > 0">
                错题本：<span class="tag warn">{{ progress.mistake_count }} 道待复练</span>
                （会间隔混入下一批）
              </template>
              <template v-else>错题本：暂无</template>
            </div>
          </div>

          <!-- 等待主管判定 -->
          <div v-if="progress.has_batch && progress.batch.status === 'awaiting_review'" class="panel-wait">
            <div class="muted" style="font-size:15px">本批 20 题已练完，等待主管判定后才能开始下一批。</div>
            <button class="btn ghost" style="margin-top:12px" @click="loadProgress">刷新状态</button>
          </div>

          <!-- 选品类开新批 -->
          <div v-else>
            <div class="field">
              <label>选择训练分类</label>
              <select class="input" v-model="selectedCatId">
                <option v-for="c in cats" :key="c.id" :value="c.id">
                  {{ c.name }}{{ c.knowledge_version ? '' : '（未提取知识库，不可训练）' }}
                </option>
              </select>
            </div>
            <button
              class="btn"
              :disabled="!canStart || starting"
              @click="onStartBatch"
            >
              {{ starting ? '组卷中...' : '开始新一批（20 题）' }}
            </button>
            <div v-if="cats.length && !cats.some(c => c.knowledge_version)" class="muted" style="margin-top:8px">
              所有分类都尚未提取知识库，请联系管理员先上传材料并提取知识。
            </div>
          </div>
        </div>

        <!-- 对话中 -->
        <div v-else>
          <div class="page-title">
            {{ session.category_name }}
            <span class="tag" v-if="isMistake" style="background:#f59e0b;color:#fff">错题复练</span>
            <span class="tag gray">第 {{ seq }}/{{ total }} 题</span>
            <span class="tag" :class="session.status === 'completed' ? 'ok' : ''">
              {{ session.status === 'completed' ? '已结束' : '训练中' }}
            </span>
          </div>
          <div v-if="questionTitle" class="muted" style="margin:-8px 0 10px">
            {{ questionTitle }}
            <span v-if="questionSkillName" class="tag" style="background:#3b82f6;color:#fff">{{ questionSkillName }}</span>
            <span v-if="questionDifficulty" class="tag gray">{{ diffLabel(questionDifficulty) }}</span>
          </div>

          <!-- 消息区 -->
          <div class="chat-box" ref="chatBox">
            <div v-for="m in messages" :key="m.id" class="msg" :class="m.role">
              <div class="bubble">{{ m.content }}</div>
            </div>
          </div>

          <!-- 快捷回复条（v0.9） -->
          <div v-if="quickReplies.length" class="quick-replies">
            <span class="muted quick-label">快捷回复</span>
            <div class="quick-scroll">
              <button
                v-for="qr in quickReplies"
                :key="qr.id"
                class="quick-chip"
                type="button"
                :disabled="sending || session.status === 'completed'"
                @click="onUseQuickReply(qr.content)"
              >
                {{ qr.content }}
              </button>
            </div>
          </div>

          <!-- 输入区 -->
          <div v-if="session.status !== 'completed'" class="row" style="margin-top:12px">
            <input
              class="input"
              v-model="inputText"
              placeholder="输入客服回复..."
              @keyup.enter="onSend"
              :disabled="sending"
            />
            <button class="btn" style="flex:0 0 auto" :disabled="!inputText.trim() || sending" @click="onSend">
              发送
            </button>
            <button class="btn ghost" style="flex:0 0 auto" @click="onFinishQuestion">
              结束本题并评分
            </button>
          </div>

          <!-- 评分 + 下一题 -->
          <div v-if="score" class="score-card">
            <div class="score-head">
              <div class="score-num" :class="scoreLevel">{{ score.total_score }}</div>
              <div>
                <div class="score-label">本题评分</div>
                <div class="muted">{{ score.summary }}</div>
              </div>
            </div>

            <!-- 维度评分 -->
            <div v-if="score.dimension_scores && Object.keys(score.dimension_scores).length" class="dim-grid">
              <div v-for="dim in dimensions" :key="dim.key" class="dim-item">
                <div class="dim-label">
                  <span>{{ dim.label }}</span>
                  <span :class="dimScoreClass(dim.key)">{{ score.dimension_scores[dim.key] || 0 }}/{{ dim.max }}</span>
                </div>
                <div class="dim-bar">
                  <div
                    class="dim-bar-fill"
                    :class="dimBarClass(dim.key)"
                    :style="{ width: dimPercent(dim.key) + '%' }"
                  ></div>
                </div>
              </div>
            </div>

            <div class="score-grid">
              <div class="score-item">
                <div class="score-title ok">✓ 做得好</div>
                <ul>
                  <li v-for="a in score.advantages" :key="a">{{ a }}</li>
                  <li v-if="!score.advantages.length" class="muted">无</li>
                </ul>
              </div>
              <div class="score-item">
                <div class="score-title err">✗ 失误遗漏</div>
                <ul>
                  <li v-for="m in score.mistakes" :key="m">{{ m }}</li>
                  <li v-if="!score.mistakes.length" class="muted">无</li>
                </ul>
              </div>
              <div class="score-item">
                <div class="score-title warn">💡 改进建议</div>
                <ul>
                  <li v-for="s in score.suggestions" :key="s">{{ s }}</li>
                  <li v-if="!score.suggestions.length" class="muted">无</li>
                </ul>
              </div>
            </div>

            <!-- 本批完成 → 提示等待判定；否则下一题 -->
            <div v-if="batchDone" class="panel-wait" style="margin-top:16px">
              <div style="font-weight:600;margin-bottom:4px">🎉 本批 {{ total }} 题已全部练完</div>
              <div class="muted">等待主管判定后才能开始下一批。</div>
            </div>
            <div v-else style="margin-top:16px">
              <div class="muted" style="margin-bottom:8px">本批已完成 {{ doneCount }}/{{ total }} 题</div>
              <button class="btn" :disabled="starting" @click="onNextQuestion">
                {{ starting ? '开题中...' : '下一题' }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  listCategoriesAgent, batchProgress, startBatch, getBatch, startBatchQuestion,
  listMessages, streamMessage, finishSession, agentQuickReplies,
} from '../api.js'

const router = useRouter()
const username = localStorage.getItem('username') || '客服'

const cats = ref([])
const selectedCatId = ref(null)
const progress = ref(null)
const starting = ref(false)

// 对话状态
const chatting = ref(false)
const session = ref(null)
const messages = ref([])
const inputText = ref('')
const sending = ref(false)
const score = ref(null)
const chatBox = ref(null)
const seq = ref(0)
const total = ref(0)
const isMistake = ref(false)
const questionTitle = ref('')
const questionSkillName = ref('')
const questionDifficulty = ref('')
const doneCount = ref(0)
const batchDone = ref(false)
const quickReplies = ref([]) // v0.9 快捷回复短语

const canStart = computed(() => {
  const c = cats.value.find(x => x.id === Number(selectedCatId.value))
  return c && c.knowledge_version > 0
})
const scoreLevel = computed(() => {
  const s = score.value?.total_score || 0
  if (s >= 80) return 'high'
  if (s >= 60) return 'mid'
  return 'low'
})

// 评分维度（从 score.scoring_dimensions 动态读取）
const dimensions = computed(() => {
  const dims = score.value?.scoring_dimensions
  if (dims && Object.keys(dims).length) {
    return Object.entries(dims).map(([key, max]) => ({ key, label: key, max }))
  }
  return [
    { key: '需求确认', label: '需求确认', max: 30 },
    { key: '产品专业', label: '产品专业', max: 25 },
    { key: '报价能力', label: '报价能力', max: 25 },
    { key: '风险控制', label: '风险控制', max: 20 },
  ]
})
function dimPercent(key) {
  const val = score.value?.dimension_scores?.[key] || 0
  const max = dimensions.find(d => d.key === key)?.max || 20
  return Math.min(100, (val / max) * 100)
}
function dimScoreClass(key) {
  const ratio = dimPercent(key)
  if (ratio >= 80) return 'ok-text'
  if (ratio >= 60) return 'warn-text'
  return 'danger-text'
}
function dimBarClass(key) {
  const ratio = dimPercent(key)
  if (ratio >= 80) return 'bar-high'
  if (ratio >= 60) return 'bar-mid'
  return 'bar-low'
}
function batchStatusLabel(s) {
  return { in_progress: '训练中', awaiting_review: '待判定', reviewed: '已判定' }[s] || s
}
function batchStatusClass(s) {
  if (s === 'awaiting_review') return 'warn'
  if (s === 'reviewed') return 'ok'
  return ''
}
function diffLabel(d) {
  return { easy: '易', medium: '中', hard: '难' }[d] || d
}

function logout() {
  localStorage.clear()
  router.push('/login')
}

// v0.9 快捷回复：点击填入输入框（空则替换，有内容则追加）
function onUseQuickReply(text) {
  const cur = inputText.value.trim()
  inputText.value = cur ? cur + ' ' + text : text
}

async function loadQuickReplies() {
  try {
    const { data } = await agentQuickReplies()
    quickReplies.value = data
  } catch (_) { /* 快捷短语加载失败不阻塞训练 */ }
}

async function scrollBottom() {
  await nextTick()
  if (chatBox.value) chatBox.value.scrollTop = chatBox.value.scrollHeight
}

async function loadCats() {
  const { data } = await listCategoriesAgent()
  cats.value = data
  const first = data.find(c => c.knowledge_version > 0)
  if (first) selectedCatId.value = first.id
}

async function loadProgress() {
  const { data } = await batchProgress()
  progress.value = data
  // 若最近一批是训练中，自动把选中品类切到该批品类
  if (data.has_batch && data.batch && data.batch.status === 'in_progress') {
    selectedCatId.value = data.batch.category_id
  }
}

async function onStartBatch() {
  if (!canStart.value) return
  starting.value = true
  try {
    const { data } = await startBatch(selectedCatId.value)
    progress.value = { has_batch: true, batch: data.batch, done_count: 0, mistake_count: 0, can_start_new: false }
    await onNextQuestion()
  } catch (e) {
    alert(e.response?.data?.detail || '开批失败')
  } finally {
    starting.value = false
  }
}

async function onNextQuestion() {
  if (!progress.value?.batch) return
  starting.value = true
  try {
    const { data } = await startBatchQuestion(progress.value.batch.id)
    session.value = data.session
    seq.value = data.seq
    total.value = data.total
    isMistake.value = data.is_mistake
    questionTitle.value = data.question.title
    questionSkillName.value = data.question.skill_name || ''
    questionDifficulty.value = data.question.difficulty || ''
    score.value = null
    batchDone.value = false
    inputText.value = ''
    chatting.value = true
    const { data: msgs } = await listMessages(data.session.id)
    messages.value = msgs
    await scrollBottom()
  } catch (e) {
    // 可能是本批已全部开始 → 刷新批次状态
    alert(e.response?.data?.detail || '开题失败')
    await loadProgress()
    if (progress.value?.batch?.status === 'awaiting_review') {
      chatting.value = false
    }
  } finally {
    starting.value = false
  }
}

async function onSend() {
  const text = inputText.value.trim()
  if (!text || sending.value) return
  sending.value = true

  messages.value.push({ id: 'agent-' + Date.now(), role: 'agent', content: text })
  inputText.value = ''

  const customerMsg = { id: 'cust-' + Date.now(), role: 'customer', content: '' }
  messages.value.push(customerMsg)
  await scrollBottom()

  let streamResult = null
  try {
    streamResult = await streamMessage(
      session.value.id,
      text,
      (token) => {
        customerMsg.content += token
        scrollBottom()
      },
      (data) => {
        streamResult = data
      }
    )

    const { data: msgs } = await listMessages(session.value.id)
    messages.value = msgs

    if (streamResult?.is_finished) {
      session.value.status = 'completed'
      await autoFinish()
    }
  } catch (e) {
    alert(typeof e === 'string' ? e : e.message || '发送失败')
    messages.value = messages.value.filter(m => m !== customerMsg)
  } finally {
    sending.value = false
    await scrollBottom()
  }
}

async function autoFinish() {
  try {
    const { data } = await finishSession(session.value.id)
    session.value = data.session
    score.value = data.score
    await refreshDoneCount()
    await scrollBottom()
  } catch (e) {
    // 自动结束失败不阻塞（可能轮数不够）
  }
}

async function onFinishQuestion() {
  if (!confirm('确认结束本题并评分？')) return
  if (sending.value) {
    sending.value = false
    try {
      const { data: msgs } = await listMessages(session.value.id)
      messages.value = msgs
    } catch (_) { /* 忽略 */ }
  }
  sending.value = true
  try {
    const { data } = await finishSession(session.value.id)
    session.value = data.session
    score.value = data.score
    await refreshDoneCount()
    await scrollBottom()
  } catch (e) {
    alert(e.response?.data?.detail || '评分失败')
  } finally {
    sending.value = false
  }
}

async function refreshDoneCount() {
  const { data } = await getBatch(progress.value.batch.id)
  progress.value.batch = data
  progress.value.done_count = data.items.filter(i => i.session_status === 'completed').length
  doneCount.value = progress.value.done_count
  batchDone.value = data.status === 'awaiting_review'
  if (batchDone.value) progress.value.has_batch = true
}

onMounted(async () => {
  await loadCats()
  await loadProgress()
  await loadQuickReplies()
})
</script>

<style scoped>
.chat-box {
  max-height: 420px;
  overflow-y: auto;
  background: var(--bg);
  border-radius: 8px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.msg { display: flex; }
.msg.agent { justify-content: flex-end; }
.msg.customer { justify-content: flex-start; }
.bubble {
  max-width: 70%;
  padding: 8px 12px;
  border-radius: 12px;
  background: var(--card);
  border: 1px solid var(--border);
  word-break: break-word;
}
.msg.agent .bubble {
  background: var(--accent, #3b82f6);
  color: #fff;
  border: none;
}
.batch-status {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 14px;
  margin-bottom: 16px;
}
.page-title-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.quick-replies {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-top: 10px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 10px;
}
.quick-label {
  flex: 0 0 auto;
  padding-top: 5px;
  font-size: 12px;
}
.quick-scroll {
  display: flex;
  gap: 6px;
  overflow-x: auto;
  padding-bottom: 2px;
}
.quick-chip {
  flex: 0 0 auto;
  border: 1px solid var(--border);
  background: var(--card);
  color: var(--text, #333);
  border-radius: 999px;
  padding: 4px 12px;
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
  max-width: 240px;
  overflow: hidden;
  text-overflow: ellipsis;
}
.quick-chip:hover {
  border-color: var(--accent, #3b82f6);
  color: var(--accent, #3b82f6);
}
.quick-chip:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.batch-status-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.panel-wait {
  background: var(--bg);
  border: 1px dashed var(--border);
  border-radius: 8px;
  padding: 16px;
  text-align: center;
}
.score-card {
  margin-top: 20px;
  border-top: 1px solid var(--border);
  padding-top: 16px;
}
.score-head {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
}
.score-num {
  font-size: 48px;
  font-weight: 700;
  line-height: 1;
}
.score-num.high { color: #22c55e; }
.score-num.mid { color: #f59e0b; }
.score-num.low { color: #ef4444; }
.score-label { font-size: 14px; color: var(--muted); }
.dim-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 16px;
  padding: 12px;
  background: var(--bg);
  border-radius: 8px;
}
.dim-label {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  margin-bottom: 4px;
  font-weight: 500;
}
.dim-bar {
  height: 8px;
  background: var(--border);
  border-radius: 4px;
  overflow: hidden;
}
.dim-bar-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.5s ease;
}
.bar-high { background: #22c55e; }
.bar-mid { background: #f59e0b; }
.bar-low { background: #ef4444; }
.score-grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 16px;
}
.score-item { background: var(--bg); padding: 12px; border-radius: 8px; }
.score-title { font-weight: 600; margin-bottom: 8px; }
.score-title.ok { color: #22c55e; }
.score-title.err { color: #ef4444; }
.score-title.warn { color: #f59e0b; }
.score-item ul { margin: 0; padding-left: 18px; }
.score-item li { margin-bottom: 4px; font-size: 14px; }
@media (max-width: 720px) {
  .score-grid { grid-template-columns: 1fr; }
}
</style>
