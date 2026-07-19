<template>
  <div>
    <div class="topbar">
      <div class="brand">客服训练系统 · 训练中心</div>
      <div class="actions">
        <span>{{ username }}</span>
        <button class="btn ghost sm" @click="logout">退出</button>
      </div>
    </div>

    <div class="container">
      <!-- 选择训练类型 -->
      <div v-if="!session" class="card">
        <div class="page-title">选择训练类型</div>
        <div class="page-sub">系统将从语料库抽取问题，由 AI 扮演客户与你对话</div>
        <div v-if="types.length" style="display: flex; gap: 12px; flex-wrap: wrap">
          <div
            v-for="t in types"
            :key="t.id"
            class="card"
            style="flex: 1 1 280px; cursor: pointer; min-width: 260px"
            @click="onStart(t)"
          >
            <div style="font-weight: 600; font-size: 16px">{{ t.name }}</div>
            <div class="muted" style="margin: 4px 0">{{ t.description || '无描述' }}</div>
            <span class="tag">{{ t.corpus_count }} 条语料</span>
          </div>
        </div>
        <div v-else class="empty">暂无训练类型，请联系管理员</div>
      </div>

      <!-- 训练中 -->
      <div v-else class="card">
        <div class="row" style="margin-bottom: 16px; align-items: center">
          <div>
            <div class="page-title" style="margin-bottom: 0">{{ currentTypeName }}</div>
            <div class="muted">
              第 {{ Math.min(progress.index + 1, progress.total) }} / {{ progress.total }} 题
              · 累计得分 {{ progress.score }}
            </div>
          </div>
          <div style="flex: 0 0 auto">
            <button class="btn ghost sm" @click="onExit">退出训练</button>
          </div>
        </div>

        <div class="chat-box" ref="chatBox">
          <div v-for="m in messages" :key="m.id" class="msg" :class="m.role">
            <div class="bubble">{{ m.content }}</div>
            <div v-if="m.role === 'agent'" class="feedback">
              <span class="score-badge" :class="{ low: m.score < 50 }">得分 {{ m.score }}</span>
              <div style="margin-top: 4px">{{ m.feedback }}</div>
            </div>
            <div v-else class="meta">AI 客户</div>
          </div>
        </div>

        <div v-if="finished" style="margin-top: 20px; text-align: center">
          <div style="font-size: 18px; margin-bottom: 12px">
            训练完成！总分
            <span class="score-badge" :class="{ low: progress.score / progress.total < 50 }">
              {{ progress.score }}
            </span>
            / {{ progress.total * 100 }}
          </div>
          <button class="btn" @click="onReset">再练一次</button>
        </div>
        <div v-else class="row" style="margin-top: 16px">
          <input
            class="input"
            v-model="answer"
            placeholder="输入你的回答..."
            @keyup.enter="onSend"
            :disabled="sending"
          />
          <button
            class="btn"
            style="flex: 0 0 auto"
            :disabled="sending || !answer.trim()"
            @click="onSend"
          >
            {{ sending ? '发送中...' : '发送' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import {
  listTrainingTypesAgent,
  startSession,
  sendMessage,
  listMessages,
} from '../api.js'

const router = useRouter()
const username = localStorage.getItem('username') || '客服'

const types = ref([])
const session = ref(null)
const messages = ref([])
const answer = ref('')
const sending = ref(false)
const finished = ref(false)
const progress = reactive({ index: 0, total: 0, score: 0 })
const chatBox = ref(null)
const currentTypeName = ref('')

function logout() {
  localStorage.clear()
  router.push('/login')
}

async function loadTypes() {
  const { data } = await listTrainingTypesAgent()
  types.value = data
}

async function onStart(t) {
  currentTypeName.value = t.name
  const { data } = await startSession(t.id)
  session.value = data
  progress.index = 0
  progress.total = data.total_questions
  progress.score = 0
  finished.value = false
  messages.value = []
  await loadMsgs(data.id)
}

async function loadMsgs(sid) {
  const { data } = await listMessages(sid)
  messages.value = data
  await scrollBottom()
}

async function onSend() {
  if (!answer.value.trim() || sending.value) return
  sending.value = true
  const content = answer.value
  answer.value = ''
  try {
    const { data } = await sendMessage(session.value.id, content)
    messages.value.push(data.agent_message)
    if (data.next_customer_message) {
      messages.value.push(data.next_customer_message)
    }
    progress.index = data.current_index
    progress.total = data.total_questions
    progress.score = data.total_score
    if (data.is_finished) {
      finished.value = true
    }
    await scrollBottom()
  } catch (e) {
    answer.value = content
    alert(e.response?.data?.detail || '发送失败')
  } finally {
    sending.value = false
  }
}

async function scrollBottom() {
  await nextTick()
  if (chatBox.value) chatBox.value.scrollTop = chatBox.value.scrollHeight
}

function onExit() {
  if (!confirm('确认退出当前训练？进度不会保存。')) return
  onReset()
}

function onReset() {
  session.value = null
  messages.value = []
  finished.value = false
  answer.value = ''
}

onMounted(loadTypes)
</script>
