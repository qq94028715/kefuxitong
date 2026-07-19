<template>
  <div>
    <div class="topbar">
      <div class="brand">客服训练系统 · 管理后台</div>
      <div class="actions">
        <span>{{ username }}</span>
        <button class="btn ghost sm" @click="logout">退出</button>
      </div>
    </div>

    <div class="container">
      <div class="card">
        <div class="tabs">
          <div class="tab" :class="{ active: tab === 'agents' }" @click="tab = 'agents'">客服账号</div>
          <div class="tab" :class="{ active: tab === 'types' }" @click="tab = 'types'">训练类型</div>
          <div class="tab" :class="{ active: tab === 'corpus' }" @click="tab = 'corpus'">语料管理</div>
        </div>

        <!-- 客服账号 -->
        <div v-if="tab === 'agents'">
          <div class="page-title">客服账号管理</div>
          <div class="page-sub">新增客服账号，供客服登录训练使用</div>
          <div class="row" style="margin-bottom: 16px">
            <input class="input" v-model="agentForm.username" placeholder="客服用户名" />
            <input class="input" v-model="agentForm.password" placeholder="密码" type="password" />
            <button class="btn" style="flex: 0 0 auto" @click="onCreateAgent">新增</button>
          </div>
          <table v-if="agents.length">
            <thead>
              <tr><th>ID</th><th>用户名</th><th>创建时间</th><th>操作</th></tr>
            </thead>
            <tbody>
              <tr v-for="a in agents" :key="a.id">
                <td>{{ a.id }}</td>
                <td>{{ a.username }}</td>
                <td>{{ fmt(a.created_at) }}</td>
                <td><button class="btn danger sm" @click="onDeleteAgent(a.id)">删除</button></td>
              </tr>
            </tbody>
          </table>
          <div v-else class="empty">暂无客服账号，请在上方新增</div>
        </div>

        <!-- 训练类型 -->
        <div v-if="tab === 'types'">
          <div class="page-title">训练类型管理</div>
          <div class="page-sub">客服登录后可选择不同训练类型进行训练</div>
          <div class="row" style="margin-bottom: 16px">
            <input class="input" v-model="typeForm.name" placeholder="训练类型名称，如：PVC训练" />
            <input class="input" v-model="typeForm.description" placeholder="描述（可选）" />
            <button class="btn" style="flex: 0 0 auto" @click="onCreateType">新增</button>
          </div>
          <table v-if="types.length">
            <thead>
              <tr><th>ID</th><th>名称</th><th>描述</th><th>语料数</th><th>操作</th></tr>
            </thead>
            <tbody>
              <tr v-for="t in types" :key="t.id">
                <td>{{ t.id }}</td>
                <td>{{ t.name }}</td>
                <td class="muted">{{ t.description || '-' }}</td>
                <td><span class="tag">{{ t.corpus_count }} 条</span></td>
                <td><button class="btn danger sm" @click="onDeleteType(t.id)">删除</button></td>
              </tr>
            </tbody>
          </table>
          <div v-else class="empty">暂无训练类型</div>
        </div>

        <!-- 语料管理 -->
        <div v-if="tab === 'corpus'">
          <div class="page-title">语料管理</div>
          <div class="page-sub">为每个训练类型维护「客户问题 + 标准回答」，AI 将基于语料训练客服</div>
          <div class="field">
            <label>选择训练类型</label>
            <select class="input" v-model="corpusTypeId" @change="loadCorpus">
              <option v-for="t in types" :key="t.id" :value="t.id">{{ t.name }}（{{ t.corpus_count }} 条）</option>
            </select>
          </div>

          <div v-if="corpusTypeId" class="card" style="background: var(--bg); margin-bottom: 16px">
            <div class="field">
              <label>客户问题</label>
              <textarea class="input" v-model="corpusForm.customer_question" placeholder="客户可能会问的问题，例如：你们的PVC板有哪些厚度？"></textarea>
            </div>
            <div class="field">
              <label>标准回答</label>
              <textarea class="input" v-model="corpusForm.standard_answer" placeholder="客服应给出的标准回答"></textarea>
            </div>
            <button class="btn" @click="onCreateCorpus">添加语料</button>
          </div>

          <table v-if="corpus.length">
            <thead>
              <tr><th>客户问题</th><th>标准回答</th><th>操作</th></tr>
            </thead>
            <tbody>
              <tr v-for="c in corpus" :key="c.id">
                <td style="max-width: 280px">{{ c.customer_question }}</td>
                <td style="max-width: 320px" class="muted">{{ c.standard_answer }}</td>
                <td><button class="btn danger sm" @click="onDeleteCorpus(c.id)">删除</button></td>
              </tr>
            </tbody>
          </table>
          <div v-else-if="corpusTypeId" class="empty">该类型暂无语料</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  listAgents,
  createAgent,
  deleteAgent,
  listTrainingTypesAdmin,
  createTrainingType,
  deleteTrainingType,
  listCorpus,
  createCorpus,
  deleteCorpus,
} from '../api.js'

const router = useRouter()
const username = localStorage.getItem('username') || '管理员'
const tab = ref('agents')

const agents = ref([])
const agentForm = reactive({ username: '', password: '' })

const types = ref([])
const typeForm = reactive({ name: '', description: '' })

const corpus = ref([])
const corpusTypeId = ref(null)
const corpusForm = reactive({ customer_question: '', standard_answer: '' })

function fmt(d) {
  if (!d) return '-'
  return new Date(d).toLocaleString('zh-CN')
}

function logout() {
  localStorage.clear()
  router.push('/login')
}

async function loadAgents() {
  const { data } = await listAgents()
  agents.value = data
}
async function onCreateAgent() {
  if (!agentForm.username || !agentForm.password) return alert('请填写用户名和密码')
  try {
    await createAgent({ ...agentForm })
    agentForm.username = ''
    agentForm.password = ''
    await loadAgents()
  } catch (e) {
    alert(e.response?.data?.detail || '新增失败')
  }
}
async function onDeleteAgent(id) {
  if (!confirm('确认删除该客服账号？')) return
  await deleteAgent(id)
  await loadAgents()
}

async function loadTypes() {
  const { data } = await listTrainingTypesAdmin()
  types.value = data
  if (!corpusTypeId.value && data.length) corpusTypeId.value = data[0].id
}
async function onCreateType() {
  if (!typeForm.name) return alert('请填写训练类型名称')
  try {
    await createTrainingType({ ...typeForm })
    typeForm.name = ''
    typeForm.description = ''
    await loadTypes()
  } catch (e) {
    alert(e.response?.data?.detail || '新增失败')
  }
}
async function onDeleteType(id) {
  if (!confirm('删除训练类型将同时删除其所有语料，确认？')) return
  await deleteTrainingType(id)
  await loadTypes()
}

async function loadCorpus() {
  if (!corpusTypeId.value) {
    corpus.value = []
    return
  }
  const { data } = await listCorpus(corpusTypeId.value)
  corpus.value = data
}
async function onCreateCorpus() {
  if (!corpusForm.customer_question || !corpusForm.standard_answer)
    return alert('请填写客户问题和标准回答')
  try {
    await createCorpus({ training_type_id: Number(corpusTypeId.value), ...corpusForm })
    corpusForm.customer_question = ''
    corpusForm.standard_answer = ''
    await loadCorpus()
    await loadTypes()
  } catch (e) {
    alert(e.response?.data?.detail || '新增失败')
  }
}
async function onDeleteCorpus(id) {
  if (!confirm('确认删除该语料？')) return
  await deleteCorpus(id)
  await loadCorpus()
  await loadTypes()
}

onMounted(async () => {
  await loadAgents()
  await loadTypes()
  await loadCorpus()
})
</script>
