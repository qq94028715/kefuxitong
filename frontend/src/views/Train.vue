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
          <div v-if="progress && progress.has_batch" class="batch-status">
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
          <div v-if="progress && progress.has_batch && progress.batch.status === 'awaiting_review'" class="panel-wait">
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

          <!-- 快捷回复条（v0.9 千牛式：分组 + 点击即发送 + 悬停预览） -->
          <div v-if="quickReplies.length" class="quick-replies">
            <div class="quick-groups">
              <button
                v-for="g in quickGroups"
                :key="g"
                class="quick-group"
                :class="{ active: activeQuickGroup === g }"
                type="button"
                @click="activeQuickGroup = g"
              >
                {{ g }}<span class="quick-count">{{ quickGroupCount(g) }}</span>
              </button>
            </div>
            <div class="quick-scroll">
              <button
                v-for="qr in filteredQuickReplies"
                :key="qr.id"
                class="quick-chip"
                type="button"
                :title="qr.content"
                :disabled="sending || session.status === 'completed'"
                @click="onUseQuickReply(qr.content)"
              >
                {{ qr.content }}
              </button>
            </div>
          </div>

          <!-- 输入区 -->
          <div v-if="session && session.status !== 'completed'" class="row" style="margin-top:12px">
            <input
              class="input"
              v-model="inputText"
              placeholder="输入客服回复..."
              @keydown="onKeydown"
              @input="onInputChange"
              @paste.prevent="onPaste"
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

          <!-- 实时键入提示（v0.11）：打字时长 + 字符数，仅在打字时展示 -->
          <div v-if="liveTyping && liveTyping.active" class="muted" style="font-size:12px;margin-top:6px">
            <span v-if="liveTyping.keystrokes > 0">
              ⌨️ 键入 {{ liveTyping.keystrokes }} 次 / {{ liveTyping.chars }} 字
              <template v-if="liveTyping.elapsedMs >= 500">
                · {{ Math.round(liveTyping.chars / liveTyping.elapsedMs * 60 * 1000) }} 字/分
              </template>
            </span>
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

            <!-- v0.11 键入统计摘要：打字速度 + 平均回复时长 -->
            <div v-if="typingStats" class="typing-summary">
              <div class="typing-stat">
                <div class="typing-num">{{ typingStats.cpm ? typingStats.cpm : '—' }}</div>
                <div class="typing-label">字/分钟</div>
                <div class="typing-sub muted">
                  {{ typingStats.validMessages }}/{{ typingStats.totalMessages }} 条有效
                </div>
              </div>
              <div class="typing-stat">
                <div class="typing-num">{{ typingStats.avgResponseSec.toFixed(1) }}秒</div>
                <div class="typing-label">平均回复时长</div>
                <div class="typing-sub muted">从客户消息到客服回复</div>
              </div>
              <div class="typing-stat">
                <div class="typing-num">{{ typingStats.quickReplyCount }}</div>
                <div class="typing-label">快捷短语</div>
                <div class="typing-sub muted">条占总数</div>
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
const progress = ref({ has_batch: false, done_count: 0, mistake_count: 0, can_start_new: true })
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
const activeQuickGroup = ref('') // 当前选中的分组

// ===================== v0.11 键入统计 =====================
// 每条客服消息采集一次：首/末次按键时间、键数、字数、粘贴标记。
// 切换对话（onNextQuestion / autoFinish / onFinishQuestion）时 reset。
const typing = ref({
  firstKeyAt: null,         // Date 首次按键
  lastKeyAt: null,          // Date 末次按键
  keystrokeCount: 0,        // 累计键数（不含 Shift/Ctrl/方向/Fn 等修饰键）
  isPaste: false,           // 是否发生粘贴
})
// 实时键入提示（用于输入框下方小字）
const liveTyping = ref({ active: false, keystrokes: 0, chars: 0, elapsedMs: 0 })
let _liveTickTimer = null

function resetTyping({ skipActiveHint = false } = {}) {
  typing.value = { firstKeyAt: null, lastKeyAt: null, keystrokeCount: 0, isPaste: false }
  if (!skipActiveHint) {
    liveTyping.value = { active: false, keystrokes: 0, chars: 0, elapsedMs: 0 }
  }
}

function _shouldCountKey(ev) {
  // 只计入「会改变输入内容」的键。修饰键、方向键、F1-F12、Esc 等不计。
  if (ev.ctrlKey || ev.metaKey || ev.altKey) return false
  const k = ev.key
  if (!k || k.length === 1) return true            // 普通字符（字母数字标点空格）
  if (k === 'Backspace' || k === 'Delete' || k === 'Enter') return true  // 删除/回车
  return false                                      // Shift / ArrowUp / Escape 等不计
}

function _startLiveTick() {
  if (_liveTickTimer) return
  _liveTickTimer = setInterval(() => {
    if (!typing.value.firstKeyAt) return
    liveTyping.value = {
      active: true,
      keystrokes: typing.value.keystrokeCount,
      chars: inputText.value.length,
      elapsedMs: Date.now() - typing.value.firstKeyAt.getTime(),
    }
  }, 300)
}
function _stopLiveTick() {
  if (_liveTickTimer) { clearInterval(_liveTickTimer); _liveTickTimer = null }
}

function onKeydown(ev) {
  // Enter 由 keyup.enter 触发 onSend；这里仅记录按键
  if (ev.key === 'Enter') return
  if (!_shouldCountKey(ev)) return
  const now = new Date()
  if (!typing.value.firstKeyAt) {
    typing.value.firstKeyAt = now
    _startLiveTick()
  }
  typing.value.lastKeyAt = now
  typing.value.keystrokeCount += 1
}

function onInputChange() {
  // v-model 已更新 inputText。这里仅记录时间兜底（一般 keydown 已先记录）
  if (!typing.value.lastKeyAt) {
    const now = new Date()
    typing.value.firstKeyAt = now
    typing.value.lastKeyAt = now
  } else {
    typing.value.lastKeyAt = new Date()
  }
}

function onPaste(ev) {
  // 粘贴：标记 isPaste=true；粘贴内容不入 keystroke 计数
  typing.value.isPaste = true
  // 让 v-model 正常更新
  const pasted = (ev.clipboardData || window.clipboardData).getData('text')
  const cur = inputText.value
  // 计算粘贴后 cursor 位置（粗略：粘贴到末尾）
  inputText.value = cur + pasted
  // 标记首末按键（粘贴也算"输入完成"）
  if (!typing.value.firstKeyAt) {
    const now = new Date()
    typing.value.firstKeyAt = now
    typing.value.lastKeyAt = now
    _startLiveTick()
  } else {
    typing.value.lastKeyAt = new Date()
  }
}

function buildTypingMetrics() {
  const t = typing.value
  const txt = inputText.value
  if (!t.firstKeyAt || !t.lastKeyAt || !txt.trim()) {
    // 没动键盘 / 空文本 → 不上报 metrics，让后端走 NULL 兼容老数据
    return null
  }
  // 快捷短语识别启发式：键数=0 且 char_count>4 且 非粘贴 → 全部由快捷短语填入
  const isQuickReply = t.keystrokeCount === 0 && !t.isPaste && txt.length > 4
  return {
    first_keystroke_at: t.firstKeyAt.toISOString(),
    last_keystroke_at: t.lastKeyAt.toISOString(),
    keystroke_count: t.keystrokeCount,
    char_count: txt.length,
    is_paste: t.isPaste,
    is_quick_reply: isQuickReply,
  }
}

// 分组列表（按短语出现顺序）
const quickGroups = computed(() => {
  const seen = []
  for (const qr of quickReplies.value) {
    const g = qr.group_name || '常用回复'
    if (!seen.includes(g)) seen.push(g)
  }
  return seen
})
// 当前分组下的短语
const filteredQuickReplies = computed(() => {
  if (!activeQuickGroup.value) return quickReplies.value
  return quickReplies.value.filter((qr) => (qr.group_name || '常用回复') === activeQuickGroup.value)
})
function quickGroupCount(g) {
  return quickReplies.value.filter((qr) => (qr.group_name || '常用回复') === g).length
}

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
  const max = dimensions.value.find(d => d.key === key)?.max || 20
  return Math.min(100, (val / max) * 100)
}

// v0.11 评分卡里的「键入统计摘要」
// 有效消息判定：keystroke_count >= 3 && char_count >= 5（排掉快捷短语/一字回复）
const typingStats = computed(() => {
  const agentMsgs = messages.value.filter(
    m => m.role === 'agent' && m.typing && m.typing.keystroke_count != null
  )
  if (!agentMsgs.length) return null
  const valid = agentMsgs.filter(m => {
    const t = m.typing
    return (t.keystroke_count || 0) >= 3 && (t.char_count || 0) >= 5 && !t.is_paste
  })
  const cpms = valid
    .map(m => m.typing.cpm)
    .filter(c => typeof c === 'number' && c > 0)
  const respMs = agentMsgs
    .map(m => m.typing.response_duration_ms)
    .filter(v => typeof v === 'number' && v >= 0 && v < 10 * 60 * 1000) // 排除 >10 分钟的怪值
  const avgCpm = cpms.length ? Math.round(cpms.reduce((a, b) => a + b, 0) / cpms.length) : null
  const avgResp = respMs.length ? respMs.reduce((a, b) => a + b, 0) / respMs.length : 0
  const quickReplyCount = agentMsgs.filter(m => m.typing.is_quick_reply).length
  return {
    cpm: avgCpm,
    avgResponseSec: avgResp / 1000,
    totalMessages: agentMsgs.length,
    validMessages: valid.length,
    quickReplyCount,
  }
})
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

// v0.9 快捷回复：千牛/拼多多式 → 文本进输入框（可编辑后再发）
function onUseQuickReply(text) {
  const cur = inputText.value
  inputText.value = cur ? cur + text : text
  // 快捷短语填入会触发 input 事件；这里明确标 is_quick_reply 候选：
  // keystroke_count=0 + 非粘贴，最终发送时 buildTypingMetrics 判定
  if (!typing.value.firstKeyAt) {
    // 没有人工输入时填入 → 当作快捷短语
    typing.value.firstKeyAt = new Date()
    typing.value.lastKeyAt = new Date()
    typing.value.keystrokeCount = 0
  }
}

async function onSend() {
  const text = inputText.value.trim()
  if (!text || sending.value) return
  sending.value = true
  const metrics = buildTypingMetrics()
  // 本地先把客服消息入栈
  const localAgentMsg = { id: 'agent-' + Date.now(), role: 'agent', content: text }
  if (metrics) {
    localAgentMsg.typing = {
      keystroke_count: metrics.keystroke_count,
      char_count: metrics.char_count,
      is_paste: metrics.is_paste,
      is_quick_reply: metrics.is_quick_reply,
    }
  }
  messages.value.push(localAgentMsg)
  inputText.value = ''
  // 重置采集（切下一条重新算）
  resetTyping({ skipActiveHint: true })
  _stopLiveTick()

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
      },
      metrics
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
    // 恢复客服消息以便用户重发
    const stored = messages.value.find(m => m === localAgentMsg)
    if (!stored) messages.value.push(localAgentMsg)
    inputText.value = text
  } finally {
    sending.value = false
    await scrollBottom()
  }
}

async function loadQuickReplies() {
  try {
    const { data } = await agentQuickReplies()
    quickReplies.value = data
    if (data.length && !activeQuickGroup.value) {
      activeQuickGroup.value = data[0].group_name || '常用回复'
    }
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
    // 新题：清空键入采集
    resetTyping()
    _stopLiveTick()
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

// 快捷回复：千牛/拼多多式 → 文本进输入框（可编辑后再发）

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
  margin-top: 10px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 10px;
}
.quick-groups {
  display: flex;
  gap: 6px;
  overflow-x: auto;
  padding-bottom: 6px;
  border-bottom: 1px dashed var(--border);
  margin-bottom: 6px;
}
.quick-group {
  flex: 0 0 auto;
  border: 1px solid var(--border);
  background: var(--card);
  color: var(--muted, #666);
  border-radius: 999px;
  padding: 3px 10px;
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
}
.quick-group.active {
  background: var(--accent, #3b82f6);
  border-color: var(--accent, #3b82f6);
  color: #fff;
  font-weight: 500;
}
.quick-count {
  margin-left: 4px;
  font-size: 11px;
  opacity: 0.7;
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
  max-width: 220px;
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
/* v0.11 键入统计摘要：评分卡顶部三块 */
.typing-summary {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 10px;
  margin-bottom: 16px;
  padding: 12px;
  background: linear-gradient(135deg, #f0f7ff 0%, #f9f5ff 100%);
  border: 1px solid #d6e4ff;
  border-radius: 8px;
}
.typing-stat {
  text-align: center;
  padding: 6px 0;
}
.typing-num {
  font-size: 22px;
  font-weight: 700;
  color: var(--accent, #3b82f6);
  line-height: 1.2;
}
.typing-label {
  font-size: 12px;
  color: var(--muted);
  margin: 2px 0 4px;
}
.typing-sub {
  font-size: 11px;
}
@media (max-width: 640px) {
  .typing-summary { grid-template-columns: 1fr; }
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
