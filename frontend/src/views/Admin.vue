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
          <div class="tab" :class="{ active: tab === 'scores' }" @click="onTabScores">训练成绩</div>
          <div class="tab" :class="{ active: tab === 'trend' }" @click="onTabTrend">成绩趋势</div>
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
                <label>上传资料文件</label>
                <input type="file" class="input" @change="onFileChange" accept=".txt,.md,.json,.docx,.pptx,.pdf,.xlsx" />
                <div class="muted" style="font-size:12px;margin-top:4px">支持 TXT / MD / DOCX / PPTX / PDF / XLSX</div>
              </div>
              <div class="row">
                <div class="field" style="flex:1">
                  <label>资料类型</label>
                  <select class="input" v-model="uploadSourceType">
                    <option value="sales">销售案例</option>
                    <option value="product">产品知识</option>
                    <option value="sop">SOP流程</option>
                    <option value="training">培训教材</option>
                    <option value="faq">FAQ</option>
                  </select>
                </div>
                <div class="field" style="flex:1" v-if="uploadSourceType === 'sales'">
                  <label>案例质量</label>
                  <select class="input" v-model="uploadQuality">
                    <option value="normal">普通</option>
                    <option value="excellent">优秀成交</option>
                    <option value="failed">失败丢单</option>
                  </select>
                </div>
              </div>
              <div class="row">
                <button class="btn" :disabled="!selectedFile || uploading" @click="onUpload">
                  {{ uploading ? '上传解析中...' : '上传资料' }}
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
                <tr><th>文件名</th><th>格式</th><th>资料类型</th><th>案例</th><th>大小</th><th>上传时间</th><th>操作</th></tr>
              </thead>
              <tbody>
                <tr v-for="m in materials" :key="m.id">
                  <td>{{ m.filename }}</td>
                  <td><span class="tag gray">{{ m.file_type }}</span></td>
                  <td><span class="tag" :class="sourceTypeTagClass(m.source_type)">{{ sourceTypeLabel(m.source_type) }}</span></td>
                  <td><span v-if="m.source_type === 'sales'" class="tag" :class="qualityTagClass(m.quality)">{{ qualityLabel(m.quality) }}</span><span v-else class="muted">-</span></td>
                  <td class="muted">{{ humanSize(m.file_size) }}</td>
                  <td>{{ fmt(m.created_at) }}</td>
                  <td>
                    <button class="btn sm" style="margin-right:6px" @click="onEditMaterial(m)">编辑</button>
                    <button class="btn danger sm" @click="onDeleteMaterial(m.id)">删除</button>
                  </td>
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
                <div v-if="knowledge.content.success_patterns?.length" class="field">
                  <label>成功模式（优秀案例提炼）</label>
                  <div v-for="(s, i) in knowledge.content.success_patterns" :key="i" class="card" style="background:var(--panel);margin-bottom:8px;padding:10px;border-left:3px solid var(--success)">
                    <div><strong>{{ s.scenario }}</strong></div>
                    <div style="font-size:13px;margin-top:4px">技巧：{{ s.technique }}</div>
                    <div v-if="s.example" style="font-size:13px;color:var(--text-soft);margin-top:2px">示例：{{ s.example }}</div>
                  </div>
                </div>
                <div v-if="knowledge.content.failure_patterns?.length" class="field">
                  <label>失败模式（丢单案例预警）</label>
                  <div v-for="(f, i) in knowledge.content.failure_patterns" :key="i" class="card" style="background:var(--panel);margin-bottom:8px;padding:10px;border-left:3px solid var(--danger)">
                    <div><strong>{{ f.scenario }}</strong></div>
                    <div style="font-size:13px;margin-top:4px;color:var(--danger)">失误：{{ f.mistake }}</div>
                    <div v-if="f.consequence" style="font-size:13px;color:var(--text-soft);margin-top:2px">后果：{{ f.consequence }}</div>
                  </div>
                </div>
                <div v-if="knowledge.content._note" class="muted" style="margin-top:8px">
                  ⚠ {{ knowledge.content._note }}
                </div>
              </div>
            </div>
            <div v-else class="empty" style="margin-top:16px">该分类尚未提取知识库，点击上方「重新提取知识库」</div>

            <!-- 编辑材料弹窗 -->
            <div v-if="editingMaterial" class="modal-overlay" @click.self="onCancelEdit">
              <div class="modal-card">
                <div class="modal-header">
                  <strong>编辑材料</strong>
                  <span class="muted" style="margin-left:12px">{{ editingMaterial.filename }}</span>
                </div>
                <div class="field">
                  <label>文件名</label>
                  <input class="input" v-model="editFilename" />
                </div>
                <div class="field">
                  <label>资料类型</label>
                  <select class="input" v-model="editSourceType">
                    <option value="sales">销售案例</option>
                    <option value="product">产品知识</option>
                    <option value="sop">SOP流程</option>
                    <option value="training">培训教材</option>
                    <option value="faq">FAQ</option>
                  </select>
                </div>
                <div v-if="editSourceType === 'sales'" class="field">
                  <label>案例质量</label>
                  <select class="input" v-model="editQuality">
                    <option value="normal">普通</option>
                    <option value="excellent">优秀成交</option>
                    <option value="failed">失败丢单</option>
                  </select>
                </div>
                <div class="field">
                  <label>内容（纯文本）</label>
                  <textarea
                    class="input mono"
                    v-model="editContent"
                    rows="16"
                    style="font-size:13px;font-family:Consolas,monospace"
                  ></textarea>
                </div>
                <div class="row" style="justify-content:flex-end;margin-top:12px">
                  <button class="btn ghost" @click="onCancelEdit">取消</button>
                  <button class="btn" :disabled="editSaving" @click="onSaveEdit">
                    {{ editSaving ? '保存中...' : '保存' }}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 训练成绩 -->
        <div v-if="tab === 'scores'">
          <div class="page-title">训练成绩查询</div>
          <div class="page-sub">查看所有客服的训练记录与 AI 评分，支持按客服/分类筛选</div>

          <!-- 筛选 -->
          <div class="row" style="margin-bottom: 16px">
            <select class="input" v-model="scoreFilter.user_id">
              <option :value="null">全部客服</option>
              <option v-for="a in agents" :key="a.id" :value="a.id">{{ a.username }}</option>
            </select>
            <select class="input" v-model="scoreFilter.category_id">
              <option :value="null">全部分类</option>
              <option v-for="c in cats" :key="c.id" :value="c.id">{{ c.name }}</option>
            </select>
            <button class="btn" style="flex: 0 0 auto" @click="loadScoreList">查询</button>
          </div>

          <!-- 列表 -->
          <table v-if="scoreList.length">
            <thead>
              <tr>
                <th>ID</th><th>客服</th><th>分类</th><th>状态</th>
                <th>消息数</th><th>分数</th><th>总评</th><th>时间</th><th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="s in scoreList" :key="s.id">
                <td>{{ s.id }}</td>
                <td>{{ s.username }}</td>
                <td>{{ s.category_name }}</td>
                <td>
                  <span v-if="s.status === 'completed'" class="tag ok">已完成</span>
                  <span v-else class="tag warn">进行中</span>
                </td>
                <td>{{ s.message_count }}</td>
                <td>
                  <strong v-if="s.score_total !== null" :class="scoreClass(s.score_total)">{{ s.score_total.toFixed(1) }}</strong>
                  <span v-else class="muted">-</span>
                </td>
                <td class="muted" style="max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{ s.score_summary || '-' }}</td>
                <td>{{ fmt(s.started_at) }}</td>
                <td><button class="btn sm" @click="onViewScore(s.id)">查看</button></td>
              </tr>
            </tbody>
          </table>
          <div v-else class="empty">暂无训练记录</div>

          <!-- 详情弹窗 -->
          <div v-if="scoreDetail" class="modal-overlay" @click.self="scoreDetail = null">
            <div class="modal-card" style="max-width:760px">
              <div class="modal-header">
                <strong>训练详情 #{{ scoreDetail.id }}</strong>
                <span class="muted" style="margin-left:12px">
                  {{ scoreDetail.username }} · {{ scoreDetail.category_name }} · {{ fmt(scoreDetail.started_at) }}
                </span>
              </div>

              <!-- 评分卡片 -->
              <div v-if="scoreDetail.score" class="card" style="background:var(--bg);margin-bottom:12px">
                <div class="row" style="align-items:center;margin-bottom:8px">
                  <div style="font-size:28px;font-weight:bold" :class="scoreClass(scoreDetail.score.total_score)">
                    {{ scoreDetail.score.total_score.toFixed(1) }}
                  </div>
                  <div class="muted" style="margin-left:8px">/ 100</div>
                </div>

                <!-- 四维评分 -->
                <div v-if="scoreDetail.score.dimension_scores && Object.keys(scoreDetail.score.dimension_scores).length" style="margin-bottom:12px">
                  <div v-for="dim in dimConfig" :key="dim.key" style="margin-bottom:6px">
                    <div style="display:flex;justify-content:space-between;font-size:13px;margin-bottom:2px">
                      <span>{{ dim.label }}</span>
                      <span :class="adminDimClass(dim.key)">{{ scoreDetail.score.dimension_scores[dim.key] || 0 }}/{{ dim.max }}</span>
                    </div>
                    <div style="height:6px;background:var(--border);border-radius:3px;overflow:hidden">
                      <div :style="{ width: adminDimPercent(dim.key) + '%', height: '100%', background: adminDimColor(dim.key), borderRadius: '3px' }"></div>
                    </div>
                  </div>
                </div>

                <div class="field">
                  <label>总评</label>
                  <div>{{ scoreDetail.score.summary }}</div>
                </div>
                <div v-if="scoreDetail.score.advantages?.length" class="field">
                  <label>优点</label>
                  <ul>
                    <li v-for="(t, i) in scoreDetail.score.advantages" :key="i" style="color:var(--success)">{{ t }}</li>
                  </ul>
                </div>
                <div v-if="scoreDetail.score.mistakes?.length" class="field">
                  <label>不足</label>
                  <ul>
                    <li v-for="(t, i) in scoreDetail.score.mistakes" :key="i" style="color:var(--danger)">{{ t }}</li>
                  </ul>
                </div>
                <div v-if="scoreDetail.score.suggestions?.length" class="field">
                  <label>建议</label>
                  <ul>
                    <li v-for="(t, i) in scoreDetail.score.suggestions" :key="i">{{ t }}</li>
                  </ul>
                </div>
              </div>
              <div v-else class="empty" style="margin-bottom:12px">该训练尚未评分</div>

              <!-- 对话记录 -->
              <div class="page-sub" style="margin-bottom:8px">对话记录（{{ scoreDetail.messages.length }} 条）</div>
              <div style="max-height:360px;overflow-y:auto">
                <div
                  v-for="m in scoreDetail.messages"
                  :key="m.id"
                  style="margin-bottom:8px;padding:8px 12px;border-radius:6px"
                  :style="m.role === 'agent' ? 'background:var(--bg)' : 'background:var(--bg-soft, #f0f7ff);border-left:3px solid var(--primary)'"
                >
                  <div class="muted" style="font-size:12px;margin-bottom:2px">
                    {{ m.role === 'agent' ? '客服' : 'AI客户' }} · {{ fmt(m.created_at) }}
                  </div>
                  <div>{{ m.content }}</div>
                </div>
              </div>

              <div class="row" style="justify-content:flex-end;margin-top:12px">
                <button class="btn ghost" @click="scoreDetail = null">关闭</button>
              </div>
            </div>
          </div>
        </div>

        <!-- 成绩趋势 -->
        <div v-if="tab === 'trend'">
          <div class="page-title">训练成绩成长趋势</div>
          <div class="page-sub">按「客服 × 分类」聚合每次训练评分，直观看培训是否有效——分数持续上升说明成长明显。</div>

          <!-- 筛选 -->
          <div class="row" style="margin-bottom: 16px">
            <select class="input" v-model="trendFilter.user_id">
              <option :value="null">全部客服</option>
              <option v-for="a in agents" :key="a.id" :value="a.id">{{ a.username }}</option>
            </select>
            <select class="input" v-model="trendFilter.category_id">
              <option :value="null">全部分类</option>
              <option v-for="c in cats" :key="c.id" :value="c.id">{{ c.name }}</option>
            </select>
            <select class="input" v-model="trendFilter.days">
              <option :value="30">最近 30 天</option>
              <option :value="90">最近 90 天</option>
              <option :value="180">最近 180 天</option>
              <option :value="365">最近 1 年</option>
            </select>
            <button class="btn" style="flex: 0 0 auto" @click="loadTrends">查询</button>
          </div>

          <!-- 成长趋势汇总卡片 -->
          <div v-if="trendSeries.length" class="trend-cards">
            <div v-for="s in trendSeries" :key="s.user_id + '-' + s.category_id" class="trend-card">
              <div class="trend-card-head">{{ s.username }} · {{ s.category_name }}</div>
              <div class="trend-card-body">
                <div class="trend-score" :class="scoreClass(s.latest_score)">
                  {{ s.latest_score != null ? s.latest_score.toFixed(1) : '-' }}
                </div>
                <div class="trend-delta" :class="trendDeltaClass(s.trend)">
                  <template v-if="s.trend === 'up'">↑ 进步 {{ s.delta.toFixed(1) }}</template>
                  <template v-else-if="s.trend === 'down'">↓ 退步 {{ Math.abs(s.delta).toFixed(1) }}</template>
                  <template v-else>→ 持平</template>
                </div>
              </div>
              <div class="trend-card-foot">共 {{ s.count }} 次训练</div>
            </div>
          </div>

          <!-- 折线图 -->
          <div v-if="trendSeries.length" ref="trendChart" class="trend-chart"></div>
          <div v-else class="empty">该筛选条件下暂无已评分的训练记录</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed, nextTick, onBeforeUnmount, watch } from 'vue'
import { useRouter } from 'vue-router'
import * as echarts from 'echarts'
import {
  listAgents, createAgent, deleteAgent,
  listCategoriesAdmin, createCategory, deleteCategory,
  listMaterials, uploadMaterial, deleteMaterial, getMaterial, updateMaterial,
  getKnowledge, extractKnowledge,
  listAdminSessions, getAdminSession, getScoreTrends,
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
const uploadQuality = ref('normal')
const uploadSourceType = ref('sales')
const extracting = ref(false)
const extractMsg = ref('')

// 编辑材料
const editingMaterial = ref(null)
const editContent = ref('')
const editFilename = ref('')
const editQuality = ref('normal')
const editSourceType = ref('sales')
const editSaving = ref(false)

// 训练成绩
const scoreList = ref([])
const scoreFilter = reactive({ user_id: null, category_id: null })
const scoreDetail = ref(null)

// 成绩趋势
const trendSeries = ref([])
const trendFilter = reactive({ user_id: null, category_id: null, days: 90 })
const trendChart = ref(null)
let trendChartInstance = null

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
function qualityLabel(q) {
  const map = { excellent: '优秀', normal: '普通', failed: '失败' }
  return map[q] || '普通'
}
function qualityTagClass(q) {
  if (q === 'excellent') return 'ok'
  if (q === 'failed') return 'warn'
  return 'gray'
}
function sourceTypeLabel(s) {
  const map = { product: '产品知识', sales: '销售案例', sop: 'SOP', training: '培训教材', faq: 'FAQ' }
  return map[s] || '销售案例'
}
function sourceTypeTagClass(s) {
  if (s === 'product') return 'ok'
  if (s === 'sop') return 'warn'
  if (s === 'faq') return 'gray'
  return ''
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
    await uploadMaterial(matCatId.value, selectedFile.value, uploadQuality.value, uploadSourceType.value)
    selectedFile.value = null
    uploadQuality.value = 'normal'
    uploadSourceType.value = 'sales'
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
async function onEditMaterial(m) {
  try {
    const { data } = await getMaterial(m.id)
    editingMaterial.value = data
    editContent.value = data.content_text || ''
    editFilename.value = data.filename || ''
    editQuality.value = data.quality || 'normal'
    editSourceType.value = data.source_type || 'sales'
  } catch (e) {
    alert(e.response?.data?.detail || '加载材料失败')
  }
}
function onCancelEdit() {
  editingMaterial.value = null
  editContent.value = ''
  editFilename.value = ''
  editQuality.value = 'normal'
  editSourceType.value = 'sales'
}
async function onSaveEdit() {
  if (!editingMaterial.value) return
  editSaving.value = true
  try {
    await updateMaterial(editingMaterial.value.id, {
      filename: editFilename.value || undefined,
      content_text: editContent.value,
      quality: editQuality.value,
      source_type: editSourceType.value,
    })
    editingMaterial.value = null
    await loadMaterials()
  } catch (e) {
    alert(e.response?.data?.detail || '保存失败')
  } finally {
    editSaving.value = false
  }
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

// ---------- 训练成绩 ----------
function onTabScores() {
  tab.value = 'scores'
  loadScoreList()
}
async function loadScoreList() {
  try {
    const params = {}
    if (scoreFilter.user_id) params.user_id = scoreFilter.user_id
    if (scoreFilter.category_id) params.category_id = scoreFilter.category_id
    const { data } = await listAdminSessions(params)
    scoreList.value = data
  } catch (e) {
    alert(e.response?.data?.detail || '加载失败')
  }
}
async function onViewScore(id) {
  try {
    const { data } = await getAdminSession(id)
    scoreDetail.value = data
  } catch (e) {
    alert(e.response?.data?.detail || '加载详情失败')
  }
}
function scoreClass(score) {
  if (score >= 80) return 'ok-text'
  if (score >= 60) return 'warn-text'
  return 'danger-text'
}
function trendDeltaClass(trend) {
  if (trend === 'up') return 'ok-text'
  if (trend === 'down') return 'danger-text'
  return 'muted'
}

// ---------- 成绩趋势 ----------
function onTabTrend() {
  tab.value = 'trend'
  loadTrends()
}
async function loadTrends() {
  try {
    const params = { days: trendFilter.days }
    if (trendFilter.user_id) params.user_id = trendFilter.user_id
    if (trendFilter.category_id) params.category_id = trendFilter.category_id
    const { data } = await getScoreTrends(params)
    trendSeries.value = data.series || []
    await nextTick()
    renderTrendChart()
  } catch (e) {
    alert(e.response?.data?.detail || '加载趋势失败')
  }
}
function renderTrendChart() {
  if (!trendChart.value) return
  if (!trendChartInstance) {
    trendChartInstance = echarts.init(trendChart.value)
  }
  // 所有系列出现的日期并集（排序去重），作为 X 轴
  const dateSet = new Set()
  trendSeries.value.forEach((s) => s.points.forEach((p) => dateSet.add(p.date)))
  const dates = Array.from(dateSet).sort()

  const palette = ['#3b82f6', '#22c55e', '#f59e0b', '#ef4444', '#a855f7', '#06b6d4', '#ec4899', '#84cc16']
  const series = trendSeries.value.map((s, idx) => {
    const map = {}
    s.points.forEach((p) => { map[p.date] = p.total_score })
    return {
      name: `${s.username}-${s.category_name}`,
      type: 'line',
      smooth: true,
      connectNulls: true,
      symbol: 'circle',
      symbolSize: 7,
      lineStyle: { width: 2 },
      itemStyle: { color: palette[idx % palette.length] },
      data: dates.map((d) => (d in map ? map[d] : null)),
    }
  })

  trendChartInstance.setOption({
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      valueFormatter: (v) => (v == null ? '-' : v.toFixed(1) + ' 分'),
    },
    legend: {
      type: 'scroll',
      top: 0,
      textStyle: { color: '#94a3b8' },
    },
    grid: { left: 48, right: 24, top: 48, bottom: 40 },
    xAxis: {
      type: 'category',
      data: dates,
      boundaryGap: false,
      axisLine: { lineStyle: { color: '#475569' } },
      axisLabel: { color: '#94a3b8' },
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: 100,
      name: '分数',
      nameTextStyle: { color: '#94a3b8' },
      axisLabel: { color: '#94a3b8' },
      splitLine: { lineStyle: { color: 'rgba(148,163,184,0.15)' } },
    },
    series,
  }, true)
  trendChartInstance.resize()
}
function disposeTrendChart() {
  if (trendChartInstance) {
    trendChartInstance.dispose()
    trendChartInstance = null
  }
}

// 四维评分配置
const dimConfig = [
  { key: '需求确认', label: '需求确认', max: 40 },
  { key: '产品知识', label: '产品知识', max: 20 },
  { key: '销售技巧', label: '销售技巧', max: 20 },
  { key: '成交推进', label: '成交推进', max: 20 },
]
function adminDimPercent(key) {
  const val = scoreDetail.value?.score?.dimension_scores?.[key] || 0
  const max = dimConfig.find(d => d.key === key)?.max || 20
  return Math.min(100, (val / max) * 100)
}
function adminDimClass(key) {
  const ratio = adminDimPercent(key)
  if (ratio >= 80) return 'ok-text'
  if (ratio >= 60) return 'warn-text'
  return 'danger-text'
}
function adminDimColor(key) {
  const ratio = adminDimPercent(key)
  if (ratio >= 80) return '#22c55e'
  if (ratio >= 60) return '#f59e0b'
  return '#ef4444'
}

onMounted(async () => {
  await loadAgents()
  await loadCats()
  window.addEventListener('resize', onTrendResize)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', onTrendResize)
  disposeTrendChart()
})
watch(tab, (v) => {
  if (v !== 'trend') disposeTrendChart()
})
function onTrendResize() {
  if (trendChartInstance) trendChartInstance.resize()
}
</script>
