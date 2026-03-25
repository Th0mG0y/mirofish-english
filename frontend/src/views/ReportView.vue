<template>
  <div class="main-view">
    <!-- Header -->
    <header class="app-header">
      <div class="header-left">
        <div class="brand" @click="router.push('/')">MIROFISH</div>
      </div>

      <div class="header-right">
        <div class="workflow-step">
          <span class="step-num">Step 4/5</span>
          <span class="step-name">Report Generation</span>
        </div>
        <div class="step-divider"></div>
        <span class="status-indicator" :class="statusClass">
          <span class="dot"></span>
          {{ statusText }}
        </span>
      </div>
    </header>

    <!-- Main Content Area -->
    <main class="content-area">
      <div class="report-panel">
        <Step4Report
          :reportId="currentReportId"
          :simulationId="simulationId"
          :reportMeta="reportMeta"
          :systemLogs="systemLogs"
          @add-log="addLog"
          @update-status="updateStatus"
        />
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Step4Report from '../components/Step4Report.vue'
import { getReport } from '../api/report'

const route = useRoute()
const router = useRouter()

// Props
const props = defineProps({
  reportId: String
})

// Data State
const currentReportId = ref(route.params.reportId)
const simulationId = ref(null)
const reportMeta = ref(null)
const systemLogs = ref([])
const currentStatus = ref('processing') // processing | completed | error
let reportPollTimer = null

// --- Status Computed ---
const statusClass = computed(() => {
  return currentStatus.value
})

const statusText = computed(() => {
  if (currentStatus.value === 'error') return 'Error'
  if (currentStatus.value === 'completed') return 'Completed'
  return 'Generating'
})

// --- Helpers ---
const addLog = (msg) => {
  const time = new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }) + '.' + new Date().getMilliseconds().toString().padStart(3, '0')
  systemLogs.value.push({ time, msg })
  if (systemLogs.value.length > 200) {
    systemLogs.value.shift()
  }
}

const updateStatus = (status) => {
  currentStatus.value = status
}

const syncStatusFromReport = (reportData) => {
  const reportStatus = reportData?.status
  if (reportStatus === 'completed') {
    currentStatus.value = 'completed'
  } else if (reportStatus === 'failed') {
    currentStatus.value = 'error'
  } else {
    currentStatus.value = 'processing'
  }
}

const stopReportPolling = () => {
  if (reportPollTimer) {
    clearInterval(reportPollTimer)
    reportPollTimer = null
  }
}

const startReportPolling = () => {
  if (reportPollTimer) return
  reportPollTimer = setInterval(async () => {
    if (!currentReportId.value) return
    try {
      const reportRes = await getReport(currentReportId.value)
      if (reportRes.success && reportRes.data) {
        reportMeta.value = reportRes.data
        simulationId.value = reportRes.data.simulation_id
        syncStatusFromReport(reportRes.data)
        if (reportRes.data.status === 'completed' || reportRes.data.status === 'failed') {
          stopReportPolling()
        }
      }
    } catch {
      // Keep polling quietly; Step4Report handles the visible progress UI.
    }
  }, 3000)
}

// --- Data Logic ---
const loadReportData = async () => {
  try {
    addLog(`Loading report data: ${currentReportId.value}`)

    // Get report info to obtain simulation_id
    const reportRes = await getReport(currentReportId.value)
    if (reportRes.success && reportRes.data) {
      const reportData = reportRes.data
      reportMeta.value = reportData
      simulationId.value = reportData.simulation_id
      syncStatusFromReport(reportData)
      if (reportData.status !== 'completed' && reportData.status !== 'failed') {
        startReportPolling()
      } else {
        stopReportPolling()
      }
    } else {
      addLog(`Failed to get report info: ${reportRes.error || 'unknown error'}`)
    }
  } catch (err) {
    addLog(`Load exception: ${err.message}`)
  }
}

// Watch route params
watch(() => route.params.reportId, (newId) => {
  if (newId && newId !== currentReportId.value) {
    currentReportId.value = newId
    stopReportPolling()
    loadReportData()
  }
}, { immediate: true })

onMounted(() => {
  addLog('ReportView initialized')
  loadReportData()
})

onUnmounted(() => {
  stopReportPolling()
})
</script>

<style scoped>
.main-view {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #FFF;
  overflow: hidden;
  font-family: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
}

/* Header */
.app-header {
  height: 60px;
  border-bottom: 1px solid #EAEAEA;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  background: #FFF;
  z-index: 100;
  position: relative;
}

.brand {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 800;
  font-size: 18px;
  letter-spacing: 1px;
  cursor: pointer;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.workflow-step {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
}

.step-num {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 700;
  color: #999;
}

.step-name {
  font-weight: 700;
  color: #000;
}

.step-divider {
  width: 1px;
  height: 14px;
  background-color: #E0E0E0;
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #666;
  font-weight: 500;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #CCC;
}

.status-indicator.processing .dot { background: #FF9800; animation: pulse 1s infinite; }
.status-indicator.completed .dot { background: #4CAF50; }
.status-indicator.error .dot { background: #F44336; }

@keyframes pulse { 50% { opacity: 0.5; } }

/* Content */
.content-area {
  flex: 1;
  position: relative;
  overflow: hidden;
}

.report-panel {
  height: 100%;
  overflow: hidden;
  width: 100%;
}
</style>
