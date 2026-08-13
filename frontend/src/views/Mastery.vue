<template>
  <div>
    <div class="topbar">
      <div class="brand">客服训练系统 · 掌握度</div>
      <div class="actions">
        <button class="btn ghost sm" @click="router.push('/train')">返回训练</button>
        <span>{{ username }}</span>
        <button class="btn ghost sm" @click="logout">退出</button>
      </div>
    </div>

    <div class="container">
      <div class="card">
        <div class="page-title">我的知识点掌握度</div>
        <div class="page-sub">AI 初评 + 主管复审后按最近判定动态更新，薄弱知识点会被优先安排进下一批训练。</div>

        <div class="field">
          <label>选择训练分类</label>
          <select class="input" v-model="catId" @change="loadMastery">
            <option v-for="c in cats" :key="c.id" :value="c.id">{{ c.name }}</option>
          </select>
        </div>

        <div v-if="loading" class="muted">加载中...</div>

        <template v-else-if="mastery">
          <div class="stat-row">
            <div class="stat"><b class="danger-text">{{ mastery.weak_count }}</b><span class="muted">薄弱</span></div>
            <div class="stat"><b class="warn-text">{{ mastery.pass_count }}</b><span class="muted">及格</span></div>
            <div class="stat"><b class="ok-text">{{ mastery.master_count }}</b><span class="muted">达标</span></div>
          </div>

          <div v-if="mastery.items.length" ref="radarEl" class="radar-wrap"></div>

          <div class="skill-list">
            <div v-for="it in mastery.items" :key="it.skill_id" class="skill-row">
              <div class="skill-name">
                <span>{{ it.skill_name }}</span>
                <span class="tag" :class="statusClass(it.status)">{{ statusLabel(it.status) }}</span>
              </div>
              <div class="skill-bar">
                <div class="skill-bar-fill" :class="barClass(it.status)" :style="{ width: it.mastery + '%' }"></div>
              </div>
              <div class="skill-num" :class="textClass(it.status)">{{ it.mastery }}%</div>
              <div class="muted skill-meta">练 {{ it.attempt_count }} 次{{ it.reject_count ? '，驳回 ' + it.reject_count : '' }}</div>
            </div>
          </div>
          <div v-if="!mastery.items.length" class="muted">
            该品类还没有知识点，等管理员上传材料并提炼后即可查看。
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import * as echarts from 'echarts'
import { listCategoriesAgent, agentMastery } from '../api.js'

const router = useRouter()
const username = localStorage.getItem('username') || '客服'

const cats = ref([])
const catId = ref(null)
const mastery = ref(null)
const loading = ref(false)
const radarEl = ref(null)
let chart = null

function statusLabel(s) {
  return { weak: '薄弱', pass: '及格', master: '达标' }[s] || s
}
function statusClass(s) {
  return { weak: 'danger', pass: 'warn', master: 'ok' }[s] || ''
}
function barClass(s) {
  return { weak: 'bar-low', pass: 'bar-mid', master: 'bar-high' }[s] || 'bar-low'
}
function textClass(s) {
  return { weak: 'danger-text', pass: 'warn-text', master: 'ok-text' }[s] || ''
}

function logout() {
  localStorage.clear()
  router.push('/login')
}

function renderRadar() {
  const items = mastery.value?.items || []
  if (!items.length) return
  nextTick(() => {
    if (!radarEl.value) return
    if (!chart) chart = echarts.init(radarEl.value)
    const max = 100
    chart.setOption({
      tooltip: {},
      radar: {
        indicator: items.map(i => ({
          name: i.skill_name.length > 8 ? i.skill_name.slice(0, 8) + '…' : i.skill_name,
          max,
        })),
        radius: '65%',
        axisName: { color: '#666', fontSize: 11 },
        splitArea: { areaStyle: { color: ['rgba(59,130,246,0.02)', 'rgba(59,130,246,0.06)'] } },
      },
      series: [{
        type: 'radar',
        data: [{
          value: items.map(i => i.mastery),
          name: '掌握度',
          areaStyle: { color: 'rgba(59,130,246,0.25)' },
          lineStyle: { color: '#3b82f6', width: 2 },
          itemStyle: { color: '#3b82f6' },
        }],
      }],
    })
  })
}

async function loadCats() {
  const { data } = await listCategoriesAgent()
  cats.value = data
  if (data.length) catId.value = data[0].id
}

async function loadMastery() {
  if (!catId.value) return
  loading.value = true
  try {
    const { data } = await agentMastery(catId.value)
    mastery.value = data
    renderRadar()
  } catch (e) {
    alert(e.response?.data?.detail || '加载掌握度失败')
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await loadCats()
  await loadMastery()
})
</script>

<style scoped>
.stat-row {
  display: flex;
  gap: 12px;
  margin: 14px 0;
}
.stat {
  flex: 1;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
  text-align: center;
}
.stat b {
  display: block;
  font-size: 24px;
}
.radar-wrap {
  width: 100%;
  height: 320px;
  margin-bottom: 8px;
}
.skill-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 12px;
}
.skill-row {
  display: flex;
  align-items: center;
  gap: 12px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
}
.skill-name {
  flex: 0 0 200px;
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.skill-bar {
  flex: 1;
  height: 8px;
  background: var(--border);
  border-radius: 4px;
  overflow: hidden;
}
.skill-bar-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.5s ease;
}
.bar-high { background: #22c55e; }
.bar-mid { background: #f59e0b; }
.bar-low { background: #ef4444; }
.skill-num {
  flex: 0 0 48px;
  text-align: right;
  font-weight: 600;
}
.skill-meta {
  flex: 0 0 110px;
  font-size: 12px;
  text-align: right;
}
.ok-text { color: #22c55e; }
.warn-text { color: #f59e0b; }
.danger-text { color: #ef4444; }
@media (max-width: 720px) {
  .skill-name { flex-basis: 120px; }
  .skill-meta { display: none; }
}
</style>
