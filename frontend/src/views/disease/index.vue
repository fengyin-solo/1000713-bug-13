<template>
  <section class="page" data-module="disease">
    <header class="page-head">
      <div>
        <h2>病害登记管理</h2>
        <p class="page-desc">维护病害记录，围绕病害编号、所在设施、病害类型、病害位置做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记病害记录</button>
        <button class="btn" type="button" @click="exportRows">导出病害登记清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in statsCards" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <div v-if="facilityStats.length" class="facility-bar">
      <span class="facility-title">按所在设施统计病害数</span>
      <span v-for="item in facilityStats" :key="item.facility" class="facility-chip">
        {{ item.facility }}：{{ item.count }} 处
      </span>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <button v-if="column === '病害编号'" class="link" type="button" @click="openDetail(row)">
              {{ row[column] ?? '—' }}
            </button>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
          <td class="row-actions">
            <button class="link" type="button" @click="openEdit(row)">编辑</button>
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无病害登记数据，可先登记病害记录</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条病害登记记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div v-if="formVisible" class="modal-mask" @click.self="closeForm">
      <div class="modal">
        <h3 class="modal-title">{{ formMode === 'create' ? '登记病害记录' : '编辑病害记录' }}</h3>
        <div v-for="field in formFields" :key="field" class="form-item">
          <label>
            <span>
              {{ field }}
              <em v-if="requiredFields.includes(field)" class="required-mark">*</em>
              <em v-if="field === '病害编号' && formMode === 'create'" class="field-hint">留空自动生成</em>
            </span>
            <input
              v-model="formValues[field]"
              :disabled="field === '病害编号' && formMode === 'edit'"
              :placeholder="`请输入${field}`"
            />
          </label>
        </div>
        <p v-if="formMode === 'create'" class="form-tip">
          同一所在设施、病害类型、病害位置重复登记时，只保留最新一次提交的内容，不另建记录。
        </p>
        <div class="modal-foot">
          <button class="btn" type="button" @click="closeForm">取消</button>
          <button class="btn primary" type="button" @click="submitForm">保存</button>
        </div>
      </div>
    </div>

    <div v-if="detailVisible" class="modal-mask" @click.self="closeDetail">
      <div class="modal">
        <h3 class="modal-title">病害记录详情</h3>
        <dl class="detail-list">
          <div v-for="field in detailFields" :key="field" class="detail-item">
            <dt>{{ field }}</dt>
            <dd>{{ detailRow[field] || '—' }}</dd>
          </div>
        </dl>
        <div class="modal-foot">
          <button class="btn" type="button" @click="closeDetail">关闭</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type FormMode = 'create' | 'edit'
interface FacilityStat { facility: string; count: number }

const ENDPOINT = '/api/disease'
const columns = ["病害编号", "所在设施", "病害类型", "病害位置", "严重等级", "发现日期", "登记人员", "病害状态"]
const actions = ["确认定级", "提交闭环", "挂起病害"]
const statuses = ["待定级", "已定级", "处置中", "已闭环", "已挂起"]

const formFields = ["病害编号", "所在设施", "病害类型", "病害位置", "严重等级", "发现日期", "登记人员"]
const requiredFields = ["病害编号", "所在设施", "病害类型"]
const detailFields = [...formFields, "病害状态"]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 1)

const statusStats = ref<Record<string, number>>({})
const facilityStats = ref<FacilityStat[]>([])
const statsCards = computed(() => [
  { label: "待定级病害", value: statusStats.value["待定级"] ?? 0 },
  { label: "处置中病害", value: statusStats.value["处置中"] ?? 0 },
  { label: "涉及设施数", value: facilityStats.value.length },
])

const formVisible = ref(false)
const formMode = ref<FormMode>('create')
const editingId = ref<number | null>(null)
const formValues = ref<Record<string, string>>({})

const detailVisible = ref(false)
const detailRow = ref<Row>({})

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function emptyForm() {
  return Object.fromEntries(formFields.map(field => [field, '']))
}

function openCreate() {
  formMode.value = 'create'
  editingId.value = null
  formValues.value = emptyForm()
  errorMessage.value = ''
  formVisible.value = true
}

function openEdit(row: Row) {
  formMode.value = 'edit'
  editingId.value = Number(row.id)
  formValues.value = Object.fromEntries(
    formFields.map(field => [field, String(row[field] ?? '')]),
  )
  errorMessage.value = ''
  formVisible.value = true
}

function closeForm() {
  formVisible.value = false
}

async function submitForm() {
  errorMessage.value = ''
  const missing = requiredFields.filter(
    field => !formValues.value[field]?.trim() && !(field === '病害编号' && formMode.value === 'create'),
  )
  if (missing.length) {
    errorMessage.value = `请填写必填字段：${missing.join('、')}`
    return
  }

  const values = Object.fromEntries(
    Object.entries(formValues.value).map(([key, value]) => [key, value.trim()]),
  )
  try {
    const url = formMode.value === 'create'
      ? ENDPOINT
      : `${ENDPOINT}/${editingId.value}`
    const response = await request(url, {
      method: formMode.value === 'create' ? 'POST' : 'PUT',
      body: JSON.stringify({ values }),
    })
    const payload = await response.json()
    if (!response.ok || payload.ok === false) {
      throw new Error(payload?.message ?? '病害记录保存失败')
    }
    formVisible.value = false
    await Promise.all([reload(), reloadStats()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '病害记录保存失败'
  }
}

async function openDetail(row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (!response.ok) {
      throw new Error('病害记录详情读取失败')
    }
    detailRow.value = await response.json()
    detailVisible.value = true
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '病害记录详情读取失败'
  }
}

function closeDetail() {
  detailVisible.value = false
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok || payload?.ok === false) {
      throw new Error(payload?.message ?? '病害登记动作未生效，请稍后重试')
    }
    await Promise.all([reload(), reloadStats()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '病害登记操作失败'
  }
}

async function reloadStats() {
  try {
    const response = await request(`${ENDPOINT}/stats`)
    if (!response.ok) {
      return
    }
    const payload = await response.json()
    statusStats.value = payload.by_status ?? {}
    facilityStats.value = payload.by_facility ?? []
  } catch {
    // 统计失败不阻断列表使用；下次刷新时再补拉。
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('病害记录列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '病害登记列表读取失败'
  }
}

onMounted(() => {
  void Promise.all([reload(), reloadStats()])
})
</script>

<style scoped>
.facility-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 12px;
  margin-bottom: 12px;
  font-size: 12px;
}
.facility-title { color: var(--muted); }
.facility-chip {
  background: #eef4ff;
  color: var(--brand);
  border-radius: 999px;
  padding: 2px 10px;
}
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}
.modal {
  width: 520px;
  max-width: calc(100vw - 32px);
  max-height: calc(100vh - 64px);
  overflow-y: auto;
  background: #fff;
  border-radius: 10px;
  padding: 18px 20px;
}
.modal-title { margin: 0 0 14px; font-size: 16px; }
.form-item { margin-bottom: 10px; }
.form-item span { display: block; font-size: 12px; color: var(--muted); margin-bottom: 4px; }
.form-item input {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 8px;
  font-size: 13px;
}
.form-item input:disabled { background: #f1f5f9; color: var(--muted); }
.required-mark { color: #b42318; font-style: normal; }
.field-hint { color: var(--muted); font-style: normal; margin-left: 6px; }
.form-tip { font-size: 12px; color: var(--muted); margin: 4px 0 12px; }
.modal-foot { display: flex; justify-content: flex-end; gap: 8px; margin-top: 6px; }
.detail-list { margin: 0; }
.detail-item {
  display: flex;
  gap: 12px;
  padding: 6px 0;
  border-bottom: 1px dashed var(--border);
  font-size: 13px;
}
.detail-item dt { width: 88px; color: var(--muted); flex-shrink: 0; }
.detail-item dd { margin: 0; }
</style>
