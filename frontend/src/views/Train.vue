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
        <!-- 选择分类 -->
        <div v-if="!session">
          <div class="page-title">开始训练</div>
          <div class="page-sub">选择一个训练分类，AI 客户将基于知识库与你模拟真实对话。</div>
          <div class="field">
            <label>选择训练分类</label>
            <select class="input" v-model="selectedCatId">
              <option v-for="c in cats" :key="c.id" :value="c.id">
                {{ c.name }}{{ c.knowledge_version ? '' : '（未提取知识库，不可训练）' }}
              </option>
            </select>
          </div>
          <button class="btn" :disabled="!canStart || starting" @click="onStart">
            {{ starting ? '创建中...' : '开始训练' }}
          </button>
          <div v-if="cats.length && !cats.some(c => c.knowledge_version)" class="muted" style="margin-top:8px">
            所有分类都尚未提取知识库，请联系管理员先上传材料并提取知识。
          </div>
        </div>

        <!-- 对话中 -->
        <div v-else>
          <div class="page-title">
            {{ session.category_name }}
            <span class="tag">{{ session.status === 'completed' ? '已结束' : '训练中' }}</span>
          </div>

          <!-- 消息区 -->
          <div class="chat-box" ref="chatBox">
            <div v-for="m in messages" :key="m.id" class="msg" :class="m.role">
              <div class="bubble">{{ m.content }}</div>
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
            <button class="btn ghost" style="flex:0 0 auto" @click="onFinish">
              结束并评分
            </button>
          </div>

          <!-- 评分 -->
          <div v-if="score" class="score-card">
            <div class="score-head">
              <div class="score-num" :class="scoreLevel">{{ score.total_score }}</div>
              <div>
                <div class="score-label">本次训练评分</div>
                <div class="muted">{{ score.summary }}</div>
              </div>
            </div>

            <!-- 四维评分 -->
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
            <button class="btn" style="margin-top:16px" @click="onReset">再练一次</button>
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
  listCategoriesAgent, startSession, listMessages,
  streamMessage, finishSession, getScore,
} from '../api.js'

const router = useRouter()
const username = localStorage.getItem('username') || '客服'

const cats = ref([])
const selectedCatId = ref(null)
const session = ref(null)
const messages = ref([])
const inputText = ref('')
const sending = ref(false)
const starting = ref(false)
const score = ref(null)
const chatBox = ref(null)

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

// 四维评分配置
const dimensions = [
  { key: '需求确认', label: '需求确认', max: 30 },
  { key: '产品专业', label: '产品专业', max: 25 },
  { key: '报价能力', label: '报价能力', max: 25 },
  { key: '风险控制', label: '风险控制', max: 20 },
]
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

function logout() {
  localStorage.clear()
  router.push('/login')
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

async function onStart() {
  if (!canStart.value) return
  starting.value = true
  try {
    const { data } = await startSession(selectedCatId.value)
    session.value = data
    const { data: msgs } = await listMessages(data.id)
    messages.value = msgs
    await scrollBottom()
  } catch (e) {
    alert(e.response?.data?.detail || '开始失败')
  } finally {
    starting.value = false
  }
}

async function onSend() {
  const text = inputText.value.trim()
  if (!text || sending.value) return
  sending.value = true

  // 先显示客服消息
  messages.value.push({ id: 'agent-' + Date.now(), role: 'agent', content: text })
  inputText.value = ''

  // 准备空的客户消息气泡（流式逐字填充）
  const customerMsg = { id: 'cust-' + Date.now(), role: 'customer', content: '' }
  messages.value.push(customerMsg)
  await scrollBottom()

  let streamResult = null
  try {
    streamResult = await streamMessage(
      session.value.id,
      text,
      // onToken: 每收到一个字符追加到气泡
      (token) => {
        customerMsg.content += token
        scrollBottom()
      },
      // onDone: 流结束
      (data) => {
        streamResult = data
      }
    )

    // 流式结束后刷新消息列表（获取真实 ID）
    const { data: msgs } = await listMessages(session.value.id)
    messages.value = msgs

    if (streamResult?.is_finished) {
      session.value.status = 'completed'
      await autoFinish()
    }
  } catch (e) {
    alert(typeof e === 'string' ? e : e.message || '发送失败')
    // 失败则移除空的气泡
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
    await scrollBottom()
  } catch (e) {
    // 自动结束失败不阻塞（可能轮数不够）
  }
}

async function onFinish() {
  if (!confirm('确认结束训练并评分？')) return
  // 如果流式消息还在发送中，强制结束（刷新消息列表对齐服务端）
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
    await scrollBottom()
  } catch (e) {
    alert(e.response?.data?.detail || '评分失败')
  } finally {
    sending.value = false
  }
}

function onReset() {
  session.value = null
  messages.value = []
  score.value = null
  inputText.value = ''
}

onMounted(loadCats)
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

/* 四维评分 */
.dim-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 16px;
  padding: 12px;
  background: var(--bg);
  border-radius: 8px;
}
.dim-item { }
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
