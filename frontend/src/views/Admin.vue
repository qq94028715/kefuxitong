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
          <div class="tab" :class="{ active: tab === 'cats' }" @click="tab = 'cats'">训练分类</div>
          <div class="tab" :class="{ active: tab === 'mat' }" @click="tab = 'mat'">材料与知识库</div>
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

        <!-- 训练分类 -->
        <div v-if="tab === 'cats'">
          <div class="page-title">训练分类管理</div>
          <div class="page-sub">客服登录后可选择不同分类进行训练。每个分类需上传材料并提取知识后才能用于训练。</div>
          <div class="row" style="margin-bottom: 16px">
            <input class="input" v-model="catForm.name" placeholder="分类名称，如：PVC训练" />
            <input class="input" v-model="catForm.description" placeholder="描述（可选）" />
            <button class="btn" style="flex: 0 0 auto" @click="onCreateCat">新增</button>
          </div>
          <table v-if="cats.length">
            <thead>
              <tr><th>ID</th><th>名称</th><th>描述</th><th>材料数</th><th>知识库</th><th>操作</th></tr>
            </thead>
            <tbody>
              <tr v-for="c in cats" :key="c.id">
                <td>{{ c.id }}</td>
                <td>{{ c.name }}</td>
                <td class="muted">{{ c.description || '-' }}</td>
                <td><span class="tag">{{ c.material_count }} 个</span></td>
                <td>
                  <span v-if="c.knowledge_version" class="tag ok">v{{ c.knowledge_version }}</span>
                  <span v-else class="tag warn">未提取</span>
                </td>
                <td><button class="btn danger sm" @click="onDeleteCat(c.id)">删除</button></td>
              </tr>
            </tbody>
          </table>
          <div v-else class="empty">暂无训练分类</div>
        </div>

        <!-- 材料与知识库 -->
        <div v-if="tab === 'mat'">
          <div class="page-title">材料与知识库</div>
          <div class="page-sub">
            上传聊天记录/产品资料（txt、md），系统自动用 AI 提炼为结构化知识库，供模拟客户与评分使用。
            <span class="muted">{{ llmHint }}</span>
          </div>

          <div class="field">
            <label>选择训练分类</label>
            <select class="input" v-model="matCatId" @change="onCatChange">
              <option v-for="c in cats" :key="c.id" :value="c.id">
                {{ c.name }}（{{ c.material_count }} 个材料 / 知识库 v{{ c.knowledge_version || 0 }}）
              </option>
            </select>
          </div>

          <div v-if="matCatId">
            <!-- 上传 -->
            <div class="card" style="background: var(--bg); margin-bottom: 16px">
              <div class="field">
                <label>上传材料文件</label>
                <input type="file" class="input" @change="onFileChange" accept=".txt,.md,.json" />
              </div>
              <div class="row">
                <button class="btn" :disabled="!selectedFile || uploading" @click="onUpload">
                  {{ uploading ? '上传中...' : '上传材料' }}
                </button>
                <button class="btn ghost" :disabled="extracting" @click="onExtract">
                  {{ extracting ? 'AI 提取中（请等待）...' : '重新提取知识库' }}
                </button>
              </div>
              <div v-if="extractMsg" class="muted" style="margin-top:8px">{{ extractMsg }}</div>
            </div>

            <!-- 材料列表 -->
            <div class="page-sub" style="margin-top:8px">已上传材料</div>
            <table v-if="materials.length">
              <thead>
                <tr><th>文件名</th><th>类型</th><th>大小</th><th>上传时间</th><th>操作</th></tr>
              </thead>
              <tbody>
                <tr v-for="m in materials" :key="m.id">
                  <td>{{ m.filename }}</td>
                  <td><span class="tag">{{ m.file_type }}</span></td>
                  <td class="muted">{{ humanSize(m.file_size) }}</td>
                  <td>{{ fmt(m.created_at) }}</td>
                  <td><button class="btn danger sm" @click="onDeleteMaterial(m.id)">删除</button></td>
                </tr>
              </tbody>
            </table>
            <div v-else class="empty">该分类暂无材料，请上传</div>

            <!-- 知识库展示 -->
            <div v-if="knowledge" style="margin-top: 20px">
              <div class="page-sub" style="margin-top:8px">
                结构化知识库
                <span class="tag ok">v{{ knowledge.version }}</span>
              </div>
              <div class="card" style="background: var(--bg)">
                <div v-if="knowledge.content.product_summary" class="field">
                  <label>产品概述</label>
                  <div>{{ knowledge.content.product_summary }}</div>
                </div>
                <div v-if="knowledge.content.required_questions?.length" class="field">
                  <label>客服必问项（评分核心依据）</label>
                  <div>
                    <span v-for="q in knowledge.content.required_questions" :key="q" class="tag" style="margin:0 6px 6px 0">{{ q }}</span>
                  </div>
                </div>
                <div v-if="knowledge.content.common_objections?.length" class="field">
                  <label>客户常见异议</label>
                  <div>
                    <span v-for="o in knowledge.content.common_objections" :key="o" class="tag warn" style="margin:0 6px 6px 0">{{ o }}</span>
                  </div>
                </div>
                <div v-if="knowledge.content.recommended_responses?.length" class="field">
                  <label>推荐应答</label>
                  <div v-for="(r, i) in knowledge.content.recommended_responses" :key="i" style="margin-bottom:6px">
                    <strong>{{ r.scenario }}：</strong>{{ r.guideline }}
                  </div>
                </div>
                <div v-if="knowledge.content.product_specs && Object.keys(knowledge.content.product_specs).length" class="field">
                  <label>产品规格</label>
                  <table>
                    <tbody>
                      <tr v-for="(v, k) in knowledge.content.product_specs" :key="k">
                        <td style="width:120px"><strong>{{ k }}</strong></td>
                        <td>{{ v }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <div v-if="knowledge.content.key_knowledge?.length" class="field">
                  <label>核心知识点</label>
                  <ul>
                    <li v-for="k in knowledge.content.key_knowledge" :key="k">{{ k }}</li>
                  </ul>
                </div>
                <div v-if="knowledge.content._note" class="muted" style="margin-top:8px">
                  ⚠ {{ knowledge.content._note }}
                </div>
              </div>
            </div>
            <div v-else class="empty" style="margin-top:16px">该分类尚未提取知识库，点击上方「重新提取知识库」</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import {
  listAgents, createAgent, deleteAgent,
  listCategoriesAdmin, createCategory, deleteCategory,
  listMaterials, uploadMaterial, deleteMaterial,
  getKnowledge, extractKnowledge,
} from '../api.js'

const router = useRouter()
const username = localStorage.getItem('username') || '管理员'
const tab = ref('agents')

const agents = ref([])
const agentForm = reactive({ username: '', password: '' })

const cats = ref([])
const catForm = reactive({ name: '', description: '' })

const matCatId = ref(null)
const materials = ref([])
const knowledge = ref(null)
const selectedFile = ref(null)
const uploading = ref(false)
const extracting = ref(false)
const extractMsg = ref('')

const llmHint = computed(() => {
  // 从根接口读 llm_enabled（简化：默认提示）
  return '配置 LLM_API_KEY 后提取为真实 AI 总结，否则为规则模式。'
})

function fmt(d) {
  if (!d) return '-'
  return new Date(d).toLocaleString('zh-CN')
}
function humanSize(b) {
  if (!b) return '-'
  if (b < 1024) return b + ' B'
  if (b < 1024 * 1024) return (b / 1024).toFixed(1) + ' KB'
  return (b / 1024 / 1024).toFixed(2) + ' MB'
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

async function loadCats() {
  const { data } = await listCategoriesAdmin()
  cats.value = data
  if (!matCatId.value && data.length) {
    matCatId.value = data[0].id
    await onCatChange()
  }
}
async function onCreateCat() {
  if (!catForm.name) return alert('请填写分类名称')
  try {
    await createCategory({ ...catForm })
    catForm.name = ''
    catForm.description = ''
    await loadCats()
  } catch (e) {
    alert(e.response?.data?.detail || '新增失败')
  }
}
async function onDeleteCat(id) {
  if (!confirm('删除分类将同时删除其所有材料与知识库，确认？')) return
  await deleteCategory(id)
  await loadCats()
}

function onFileChange(e) {
  selectedFile.value = e.target.files[0] || null
}
async function onUpload() {
  if (!selectedFile.value || !matCatId.value) return
  uploading.value = true
  try {
    await uploadMaterial(matCatId.value, selectedFile.value)
    selectedFile.value = null
    await loadMaterials()
    await loadCats()
  } catch (e) {
    alert(e.response?.data?.detail || '上传失败')
  } finally {
    uploading.value = false
  }
}
async function loadMaterials() {
  if (!matCatId.value) return
  const { data } = await listMaterials(matCatId.value)
  materials.value = data
}
async function loadKnowledge() {
  if (!matCatId.value) return
  try {
    const { data } = await getKnowledge(matCatId.value)
    knowledge.value = data
  } catch (e) {
    if (e.response?.status === 404) knowledge.value = null
    else throw e
  }
}
async function onCatChange() {
  await Promise.all([loadMaterials(), loadKnowledge()])
}
async function onDeleteMaterial(id) {
  if (!confirm('确认删除该材料？')) return
  await deleteMaterial(id)
  await loadMaterials()
  await loadCats()
}
async function onExtract() {
  if (!matCatId.value) return
  if (!confirm('将用 AI 从当前所有材料重新提取知识库（会生成新版本），确认？')) return
  extracting.value = true
  extractMsg.value = ''
  try {
    const { data } = await extractKnowledge(matCatId.value)
    extractMsg.value = data.message
    await loadKnowledge()
    await loadCats()
  } catch (e) {
    alert(e.response?.data?.detail || '提取失败')
  } finally {
    extracting.value = false
  }
}

onMounted(async () => {
  await loadAgents()
  await loadCats()
})
</script>
