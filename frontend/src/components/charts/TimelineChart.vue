<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { G2Spec } from '@antv/g2'
import type { ReleaseRecord } from '@/services/types'
import DateRangeSlider from './DateRangeSlider.vue'
import G2Chart from './G2Chart.vue'

const props = withDefaults(defineProps<{ releases: ReleaseRecord[]; height?: number; compact?: boolean }>(), { height: 220, compact: false })
const DAY = 86_400_000
const eventDates = computed(() => props.releases
  .map((release) => release.publishedAt.slice(0, 10))
  .filter((date) => /^\d{4}-\d{2}-\d{2}$/.test(date))
  .sort())
const minDate = computed(() => eventDates.value[0] ?? '')
const maxDate = computed(() => eventDates.value.at(-1) ?? '')
const startDate = ref('')
const endDate = ref('')

watch([minDate, maxDate], ([min, max]) => {
  if (!min || !max) { startDate.value = ''; endDate.value = ''; return }
  const latest = Date.parse(max + 'T00:00:00Z')
  startDate.value = new Date(Math.max(Date.parse(min + 'T00:00:00Z'), latest - 90 * DAY)).toISOString().slice(0, 10)
  endDate.value = max
}, { immediate: true })

const range = computed(() => {
  if (!startDate.value || !endDate.value || startDate.value > endDate.value) return null
  return { start: Date.parse(startDate.value + 'T00:00:00Z'), end: Date.parse(endDate.value + 'T00:00:00Z') + DAY }
})
const bucketSize = computed<'week' | 'month' | 'quarter'>(() => {
  const span = range.value ? range.value.end - range.value.start : 0
  if (span <= 60 * DAY) return 'week'
  if (span <= 3 * 365 * DAY) return 'month'
  return 'quarter'
})

function bucketStart(timestamp: number, size: 'week' | 'month' | 'quarter') {
  const date = new Date(timestamp)
  const year = date.getUTCFullYear()
  const month = date.getUTCMonth()
  if (size === 'week') {
    const day = date.getUTCDay()
    return Date.UTC(year, month, date.getUTCDate() - ((day + 6) % 7))
  }
  if (size === 'month') return Date.UTC(year, month, 1)
  return Date.UTC(year, Math.floor(month / 3) * 3, 1)
}

const labelsByBucket = computed(() => {
  if (!range.value) return new Map<number, string>()
  const firstYear = new Date(range.value.start).getUTCFullYear()
  const lastYear = new Date(range.value.end - 1).getUTCFullYear()
  const spansYears = firstYear !== lastYear
  const labels = new Map<number, string>()
  let cursor = bucketStart(range.value.start, bucketSize.value)
  const last = bucketStart(range.value.end - 1, bucketSize.value)

  while (cursor <= last) {
    const date = new Date(cursor)
    const year = date.getUTCFullYear()
    const month = String(date.getUTCMonth() + 1).padStart(2, '0')
    const day = String(date.getUTCDate()).padStart(2, '0')
    const label = bucketSize.value === 'week'
      ? `${spansYears ? `${String(year).slice(-2)}/` : ''}${month}/${day}`
      : bucketSize.value === 'month'
        ? spansYears ? `${year}/${month}` : `${month}月`
        : `${year} Q${Math.floor(date.getUTCMonth() / 3) + 1}`
    labels.set(cursor, label)
    if (bucketSize.value === 'week') cursor += 7 * DAY
    else if (bucketSize.value === 'month') cursor = Date.UTC(year, date.getUTCMonth() + 1, 1)
    else cursor = Date.UTC(year, date.getUTCMonth() + 3, 1)
  }
  return labels
})

const rows = computed(() => {
  if (!range.value) return []
  const counts = new Map<number, { formal: number; prerelease: number }>()
  for (const bucket of labelsByBucket.value.keys()) counts.set(bucket, { formal: 0, prerelease: 0 })

  for (const release of props.releases) {
    const timestamp = Date.parse(release.publishedAt)
    if (!Number.isFinite(timestamp) || timestamp < range.value.start || timestamp >= range.value.end) continue
    const bucket = bucketStart(timestamp, bucketSize.value)
    const count = counts.get(bucket)
    if (!count) continue
    if (release.prerelease) count.prerelease += 1
    else count.formal += 1
  }

  return [...counts.entries()].flatMap(([bucket, count]) => {
    const label = labelsByBucket.value.get(bucket) ?? ''
    return [
      { label, kind: '正式版', count: count.formal },
      { label, kind: '预发布版', count: count.prerelease },
    ]
  })
})
const maxBucketCount = computed(() => Math.max(0, ...rows.value.map((row) => row.count)))

const spec = computed<G2Spec>(() => ({
  type: 'interval',
  data: rows.value,
  transform: [{ type: 'dodgeX' }],
  encode: { x: 'label', y: 'count', color: 'kind' },
  scale: {
    color: { domain: ['正式版', '预发布版'], range: ['#4d819b', '#ce3f7c'] },
    x: { padding: 0.16 },
    y: { domainMin: 0, nice: false, tickCount: Math.max(1, Math.min(5, maxBucketCount.value)) },
  },
  axis: {
    x: { title: false, label: !props.compact, labelFontSize: 9, labelAutoRotate: false },
    y: { title: props.compact ? false : 'Release 数', gridLineDash: [3, 3] },
  },
  legend: props.compact ? false : { color: { position: 'bottom', itemLabelFontSize: 10 } },
  tooltip: { title: 'label', items: [{ field: 'kind', name: '版本类型' }, { field: 'count', name: 'Release 数' }] },
}))

</script>

<template>
  <div class="release-timeline" data-testid="release-timeline">
    <div v-if="!compact" class="release-timeline__range">
      <DateRangeSlider v-model:start-date="startDate" v-model:end-date="endDate" :min-date="minDate" :max-date="maxDate" range-label="发布时间线日期范围" />
    </div>
    <G2Chart v-if="rows.some((row) => row.count > 0)" :spec="spec" label="按周、月或季度统计的正式版与预发布版数量" :height="height" />
    <div v-else class="release-timeline__empty" :style="{ height: `${height}px` }">所选日期范围内没有已采集的 Release 记录</div>
  </div>
</template>

<style scoped>
.release-timeline { display:grid; gap:8px; min-width:0; }
.release-timeline__range { min-width:0; }
.release-timeline__empty { display:grid; place-items:center; color:var(--muted); font-size:11px; text-align:center; }
</style>
