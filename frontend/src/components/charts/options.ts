import type { EChartsOption } from 'echarts'
import type { HistogramBucket, NamedSeries, ReleaseRecord, ResearchScatterPoint, TimePoint } from '@/services/types'
import { fontFamily, MONO, type ChartTheme } from './theme'

const mmdd = (iso: string) => iso.slice(5)
const tip = (t: ChartTheme) => ({
  backgroundColor: t.panel,
  borderColor: t.border,
  borderWidth: 1,
  padding: [9, 11] as [number, number],
  textStyle: { color: t.ink, fontSize: 11.5, fontFamily },
  extraCssText: `border-radius:8px;box-shadow:${t.dark ? '0 8px 24px rgba(0,0,0,.5)' : '0 6px 18px rgba(0,0,0,.12)'};`,
})
const axis = (t: ChartTheme) => ({
  axisLine: { lineStyle: { color: t.border } },
  axisTick: { show: false },
  axisLabel: { color: t.muted, fontSize: 10, fontFamily: MONO },
  splitLine: { lineStyle: { color: t.grid } },
})

export function timeSeriesOption(points: TimePoint[], unit: string, color: string, t: ChartTheme, dense = false, movingAverageWindow = 0): EChartsOption {
  const averageName = `${movingAverageWindow} 周均值`
  const observedName = movingAverageWindow > 1 ? '每周提交' : unit
  const movingAverage = movingAverageWindow > 1
    ? points.map((_, index) => {
      const window = points.slice(index - movingAverageWindow + 1, index + 1)
      if (window.length !== movingAverageWindow || window.some((item) => item.value === null || item.quality !== 'ready' || item.completeWeek !== true)) return null
      return window.reduce((sum, item) => sum + (item.value ?? 0), 0) / movingAverageWindow
    })
    : []
  return {
    animation: false,
    grid: { left: 44, right: 12, top: movingAverageWindow > 1 ? 34 : 16, bottom: 26 },
    legend: movingAverageWindow > 1 ? {
      top: 0, left: 0, icon: 'roundRect', itemWidth: 8, itemHeight: 8, itemGap: 14,
      textStyle: { color: t.muted, fontSize: 10.5, fontFamily },
      data: [observedName, averageName],
    } : undefined,
    tooltip: {
      ...tip(t),
      trigger: 'axis',
      axisPointer: { type: 'line', lineStyle: { color: t.border, width: 1 } },
      formatter: (params: unknown) => {
        const rows = params as { axisValue: string; dataIndex: number; seriesName: string; value: number | null; color: string }[]
        const point = points[rows[0]?.dataIndex]
        const header = `<div style="color:${t.muted};font-size:10.5px;font-family:${MONO};margin-bottom:4px">${rows[0]?.axisValue}</div>`
        return header + rows.map((row) => {
          const observed = row.seriesName === observedName && point?.value === null && point.observedValue != null
          const value = observed ? point?.observedValue : row.value
          const display = value === null || value === undefined
            ? row.seriesName === averageName ? `未计算（需连续完整 ${movingAverageWindow} 周）` : '未覆盖'
            : `${Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 1 })} ${unit}`
          const note = observed ? `<div style="color:${t.ink};font-size:10px;margin:2px 0 4px 14px">仅显示已观察数量，覆盖不完整</div>` : ''
          return `<div style="display:flex;justify-content:space-between;gap:16px"><span><i style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${row.color};margin-right:6px"></i>${row.seriesName}</span><b>${display}</b></div>${note}`
        }).join('')
      },
    },
    xAxis: { type: 'category', data: points.map((p) => mmdd(p.date)), ...axis(t), axisLine: { lineStyle: { color: t.border } }, splitLine: { show: false } },
    yAxis: { type: 'value', ...axis(t), axisLine: { show: false } },
    series: [
      {
        name: observedName,
        type: dense ? 'line' : 'bar',
        data: points.map((p) => ({
          value: p.value ?? p.observedValue ?? null,
          ...(p.value === null && p.observedValue != null ? { itemStyle: { opacity: 0.55 } } : {}),
        })),
        itemStyle: { color, borderRadius: dense ? undefined : [3, 3, 0, 0] },
        lineStyle: { color, width: 2 },
        symbol: 'circle', symbolSize: 4, showSymbol: false,
        areaStyle: dense ? { opacity: 0.12, color } : undefined,
        emphasis: { itemStyle: { color } },
      },
      ...(movingAverageWindow > 1 ? [{
        name: averageName,
        type: 'line' as const,
        data: movingAverage,
        symbol: 'circle',
        symbolSize: 5,
        showSymbol: true,
        connectNulls: false,
        lineStyle: { color: t.series[3], width: 2 },
        itemStyle: { color: t.series[3] },
        z: 3,
      }] : []),
    ],
  }
}

export function groupedOption(series: NamedSeries[], unit: string, colors: string[], t: ChartTheme, legend = true, compact = false): EChartsOption {
  const dates = series[0]?.points.map((p) => p.date) ?? []
  return {
    animation: false,
    grid: { left: compact ? 10 : 44, right: 12, top: 12, bottom: legend ? 46 : 26 },
    legend: legend ? {
      bottom: 0, left: 0, icon: 'roundRect', itemWidth: 8, itemHeight: 8, itemGap: 16,
      textStyle: { color: t.muted, fontSize: 11, fontFamily }, selectedMode: true,
    } : undefined,
    tooltip: {
      ...tip(t), trigger: 'axis', axisPointer: { type: 'line', lineStyle: { color: t.border, width: 1 } },
      formatter: (params: unknown) => {
        const rows = params as { axisValue: string; dataIndex: number; seriesName: string; value: number | null; color: string }[]
        return `<div style="color:${t.muted};font-size:10.5px;font-family:${MONO};margin-bottom:4px">${rows[0]?.axisValue}</div>` +
          rows.map((r) => {
            const point = series.find((item) => item.label === r.seriesName)?.points[r.dataIndex]
            const observed = point?.value === null && point.observedValue != null
            const value = observed ? point.observedValue : r.value
            return `<div style="display:flex;justify-content:space-between;gap:16px"><span><i style="display:inline-block;width:8px;height:8px;border-radius:2px;background:${r.color};margin-right:6px"></i>${r.seriesName}</span><b>${value === null ? '未覆盖' : `${value} ${unit}`}</b></div>${observed ? `<div style="color:${t.ink};font-size:10px;margin:2px 0 4px 14px">仅显示已观察数量，覆盖不完整</div>` : ''}`
          }).join('')
      },
    },
    xAxis: { type: 'category', data: dates.map(mmdd), ...axis(t), splitLine: { show: false } },
    yAxis: compact
      ? { type: 'value', show: false }
      : { type: 'value', ...axis(t), axisLine: { show: false } },
    series: series.map((s, i) => ({
      name: s.label, type: 'bar', barGap: '12%', barMaxWidth: 12,
      data: s.points.map((p) => ({
        value: p.value ?? p.observedValue ?? null,
        ...(p.value === null && p.observedValue != null ? { itemStyle: { opacity: 0.55 } } : {}),
      })),
      itemStyle: { color: colors[i] ?? t.series[i], borderRadius: [2, 2, 0, 0] },
    })),
  }
}

export function histogramOption(buckets: HistogramBucket[], color: string, t: ChartTheme, unit = '条记录'): EChartsOption {
  const total = buckets.reduce((sum, bucket) => sum + bucket.count, 0)
  let cumulative = 0
  const cumulativePercent = buckets.map((bucket) => {
    cumulative += bucket.count
    return total ? Number((cumulative / total * 100).toFixed(1)) : null
  })
  return {
    animation: false,
    grid: { left: 40, right: 44, top: 30, bottom: 30 },
    legend: {
      top: 0, left: 0, icon: 'roundRect', itemWidth: 8, itemHeight: 8, itemGap: 14,
      textStyle: { color: t.muted, fontSize: 10.5, fontFamily },
      data: ['样本数', '累计占比'],
    },
    tooltip: {
      ...tip(t), trigger: 'axis', axisPointer: { type: 'line', lineStyle: { color: t.border, width: 1 } },
      formatter: (params: unknown) => {
        const rows = params as { axisValue: string; seriesName: string; value: number | null }[]
        const count = rows.find((row) => row.seriesName === '样本数')?.value
        const percent = rows.find((row) => row.seriesName === '累计占比')?.value
        return `<div style="color:${t.muted};font-size:10.5px;margin-bottom:3px">${rows[0]?.axisValue}</div><div>样本数：<b>${count ?? 0}</b> ${unit}</div><div>累计占比：<b>${percent === null || percent === undefined ? '—' : `${percent}%`}</b></div>`
      },
    },
    xAxis: { type: 'category', data: buckets.map((b) => b.label), ...axis(t), splitLine: { show: false }, axisLabel: { color: t.muted, fontSize: 10, fontFamily } },
    yAxis: [
      { type: 'value', name: '样本数', nameTextStyle: { color: t.muted, fontSize: 9.5 }, ...axis(t), axisLine: { show: false } },
      { type: 'value', name: '%', min: 0, max: 100, interval: 25, position: 'right', axisLine: { show: false }, axisTick: { show: false }, splitLine: { show: false }, axisLabel: { color: t.muted, fontSize: 9.5, formatter: (value: number) => `${value}%` } },
    ],
    series: [
      {
        name: '样本数',
        type: 'bar', barMaxWidth: 46,
        data: buckets.map((b) => b.count),
        itemStyle: { color, borderRadius: [3, 3, 0, 0] },
        label: { show: true, position: 'top', color: t.muted, fontSize: 10, fontFamily: MONO },
      },
      {
        name: '累计占比',
        type: 'line', yAxisIndex: 1,
        data: cumulativePercent,
        step: 'end',
        symbol: 'circle', symbolSize: 5,
        lineStyle: { color: t.series[3], width: 2 },
        itemStyle: { color: t.series[3] },
        connectNulls: false,
      },
    ],
  }
}

export function timelineOption(releases: ReleaseRecord[], t: ChartTheme, compact = false): EChartsOption {
  const formal = releases.filter((r) => !r.prerelease)
  const pre = releases.filter((r) => r.prerelease)
  const releaseTimes = releases.map((release) => Date.parse(release.publishedAt)).filter(Number.isFinite)
  const earliest = Math.min(...releaseTimes)
  const latest = Math.max(...releaseTimes)
  const span = latest - earliest
  const start = span > 90 * 24 * 60 * 60 * 1000 ? Math.max(0, (latest - 90 * 24 * 60 * 60 * 1000 - earliest) / span * 100) : 0
  const releasesByDate = new Map<string, ReleaseRecord[]>()
  for (const release of releases) {
    const date = release.publishedAt.slice(0, 10)
    releasesByDate.set(date, [...(releasesByDate.get(date) ?? []), release])
  }
  const verticalOffset = new Map<ReleaseRecord, number>()
  for (const sameDay of releasesByDate.values()) {
    const step = Math.min(0.18, 1.3 / Math.max(1, sameDay.length - 1))
    sameDay.forEach((release, index) => verticalOffset.set(release, (index - (sameDay.length - 1) / 2) * step))
  }
  const data = (rows: ReleaseRecord[]) => rows.map((r) => ({ name: r.tag, value: [r.publishedAt, 1 + (verticalOffset.get(r) ?? 0)], itemStyle: { color: r.prerelease ? t.panel : t.series[2], borderColor: r.prerelease ? t.series[3] : t.series[2], borderWidth: 2 } }))
  return {
    animation: false,
    grid: { left: 20, right: 20, top: 22, bottom: compact ? 28 : 50 },
    tooltip: {
      ...tip(t),
      trigger: 'item',
      formatter: (params: unknown) => {
        const p = (Array.isArray(params) ? params[0] : params) as { name?: string; seriesName?: string; value?: [string | number, number] } | undefined
        if (!p) return ''
        const escape = (value: string) => value.replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]!)
        const date = String(p.value?.[0] ?? '').slice(0, 10)
        return `<div style="font-family:${MONO};font-size:11px">${escape(p.name ?? 'Release')}</div><div style="color:${t.ink};font-size:11px;margin-top:2px">${escape(date)} · ${escape(p.seriesName ?? '')}</div>`
      },
    },
    xAxis: {
      type: 'time', ...axis(t), splitLine: { show: false },
      splitNumber: 5,
      axisLabel: {
        show: !compact,
        hideOverlap: true,
        color: t.ink,
        formatter: (value: number) => {
          const date = new Date(value)
          return `${String(date.getUTCMonth() + 1).padStart(2, '0')}-${String(date.getUTCDate()).padStart(2, '0')}`
        },
      },
      axisTick: { show: !compact },
    },
    yAxis: { type: 'value', min: 0, max: 2, show: false },
    dataZoom: compact || releases.length < 2 ? undefined : [
      { type: 'inside', xAxisIndex: 0, filterMode: 'none', start, end: 100, zoomOnMouseWheel: true, moveOnMouseWheel: true, moveOnMouseMove: true },
      {
        type: 'slider', xAxisIndex: 0, filterMode: 'none', start, end: 100,
        height: 14, bottom: 1, showDetail: false, showDataShadow: false, brushSelect: false,
        borderColor: t.border, backgroundColor: t.soft,
        fillerColor: t.dark ? 'rgba(242,148,194,.2)' : 'rgba(206,63,124,.16)',
        handleStyle: { color: t.series[2], borderColor: t.border },
      },
    ],
    series: [
      { name: '正式发布', type: 'scatter', symbolSize: compact ? 9 : 11, data: data(formal), emphasis: { scale: true }, label: { show: !compact && formal.length <= 8, position: 'top', formatter: (p: { name: string }) => p.name, color: t.muted, fontSize: 9.5, fontFamily: MONO } },
      { name: '预发布', type: 'scatter', symbolSize: compact ? 8 : 10, data: data(pre), emphasis: { scale: true } },
    ],
  }
}

export function comparisonOption(entries: { label: string; color: string; points: TimePoint[] }[], t: ChartTheme): EChartsOption {
  const dates = [...new Set(entries.flatMap((entry) => entry.points.map((point) => point.date)))].sort()
  return {
    animation: false,
    grid: { left: 44, right: 12, top: 12, bottom: 46 },
    legend: { bottom: 0, left: 0, icon: 'roundRect', itemWidth: 8, itemHeight: 8, itemGap: 16, textStyle: { color: t.muted, fontSize: 11, fontFamily } },
    tooltip: {
      ...tip(t), trigger: 'axis',
      formatter: (params: unknown) => {
        const rows = params as { axisValue: string; seriesName: string; value: number; color: string }[]
        return `<div style="color:${t.muted};font-size:10.5px;font-family:${MONO};margin-bottom:4px">${rows[0]?.axisValue}</div>` +
          rows.filter((r) => r.value != null).map((r) => `<div style="display:flex;justify-content:space-between;gap:16px"><span><i style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${r.color};margin-right:6px"></i>${r.seriesName}</span><b>${r.value}</b></div>`).join('')
      },
    },
    xAxis: { type: 'category', data: dates.map(mmdd), ...axis(t), splitLine: { show: false } },
    yAxis: { type: 'value', ...axis(t), axisLine: { show: false } },
    series: entries.map((e) => {
      const map = new Map(e.points.map((p) => [p.date, p.value]))
      return {
        name: e.label, type: 'line', connectNulls: false, symbol: 'circle', symbolSize: 4,
        data: dates.map((d) => map.get(d) ?? null),
        lineStyle: { color: e.color, width: 2 }, itemStyle: { color: e.color },
      }
    }),
  }
}

export function scatterOption(points: ResearchScatterPoint[], groups: string[], colors: string[], t: ChartTheme): EChartsOption {
  const xValues = points.map((point) => point.issueCloseDays).sort((a, b) => a - b)
  const yValues = points.map((point) => point.prMergeDays).sort((a, b) => a - b)
  const medianOf = (values: number[]) => {
    if (!values.length) return null
    const middle = Math.floor(values.length / 2)
    return values.length % 2 ? values[middle] : (values[middle - 1] + values[middle]) / 2
  }
  const issueMedian = medianOf(xValues)
  const prMedian = medianOf(yValues)
  return {
    animation: false,
    grid: { left: 44, right: 16, top: 16, bottom: 46 },
    legend: { bottom: 0, left: 0, icon: 'circle', itemWidth: 8, itemHeight: 8, itemGap: 16, textStyle: { color: t.muted, fontSize: 11, fontFamily }, data: groups },
    tooltip: {
      ...tip(t),
      formatter: (params: unknown) => {
        const p = (Array.isArray(params) ? params[0] : params) as { data: { name: string; value: number[] } }
        const point = points.find((item) => item.repository === p.data.name)
        return `<div style="font-family:${MONO};font-size:11px">${p.data.name}</div><div style="color:${t.muted};font-size:11px;margin-top:3px">Issue 关闭 P50：${p.data.value[0].toLocaleString('zh-CN', { maximumFractionDigits: 1 })} 天 · n=${point?.issueSample ?? '—'}</div><div style="font-size:11px">PR 合并 P50：${p.data.value[1].toLocaleString('zh-CN', { maximumFractionDigits: 1 })} 天 · n=${point?.prSample ?? '—'}</div>`
      },
    },
    xAxis: { type: 'value', name: 'Issue 关闭天数', nameTextStyle: { color: t.muted, fontSize: 10 }, ...axis(t) },
    yAxis: { type: 'value', name: 'PR 合并天数', nameTextStyle: { color: t.muted, fontSize: 10 }, ...axis(t), axisLine: { show: false } },
    series: [
      ...groups.map((g, i) => ({
        name: g, type: 'scatter' as const,
        symbolSize: (value: number[]) => Math.min(24, 8 + Math.sqrt(Math.max(0, value[2] ?? 0)) * 1.5),
        data: points.filter((p) => p.group === g).map((p) => ({ name: p.repository, value: [p.issueCloseDays, p.prMergeDays, Math.min(p.issueSample, p.prSample)] })),
        itemStyle: { color: colors[i] ?? t.series[i], opacity: 0.8 },
      })),
      ...(issueMedian !== null && prMedian !== null ? [{
        name: '样本中位数', type: 'line' as const, data: [], symbol: 'none', silent: true,
        tooltip: { show: false },
        markLine: {
          silent: true, symbol: 'none',
          lineStyle: { color: t.muted, type: 'dashed' as const, width: 1 },
          label: { show: false },
          data: [{ xAxis: issueMedian }, { yAxis: prMedian }],
        },
      }] : []),
    ],
  }
}

export function calendarOption(points: TimePoint[], t: ChartTheme, windowStart?: string | null, windowEnd?: string | null, width = 0): EChartsOption {
  const dates = points.map((point) => point.date).filter((value) => Number.isFinite(Date.parse(value))).sort()
  const startTime = windowStart ? Date.parse(windowStart) : NaN
  const endTime = windowEnd ? Date.parse(windowEnd) : NaN
  const validWindow = Number.isFinite(startTime) && Number.isFinite(endTime) && endTime > startTime
  const start = validWindow ? new Date(startTime).toISOString().slice(0, 10) : dates[0] ?? ''
  const end = validWindow ? new Date(endTime - 1).toISOString().slice(0, 10) : dates[dates.length - 1] ?? ''
  const visiblePoints = points.filter((point) => point.date >= start && point.date <= end && point.value !== null)
  const max = Math.max(...visiblePoints.map((point) => point.value ?? 0), 1)
  const startDay = Date.parse(`${start}T00:00:00Z`)
  const endDay = Date.parse(`${end}T00:00:00Z`)
  const days = Number.isFinite(startDay) && Number.isFinite(endDay) ? Math.floor((endDay - startDay) / 86400000) + 1 : 1
  const weeks = Math.max(1, Math.ceil((new Date(startDay).getUTCDay() + days) / 7))
  const cellSize = width > 0 ? Math.max(5, Math.min(20, Math.floor((width - 48) / weeks))) : 14
  const left = width > 0 ? Math.max(24, Math.floor((width - weeks * cellSize) / 2)) : 24
  return {
    animation: false,
    tooltip: {
      ...tip(t),
      formatter: (params: unknown) => {
        const p = (Array.isArray(params) ? params[0] : params) as { value?: [string, number] } | undefined
        if (!p?.value) return ''
        return `<div style="font-family:${MONO};font-size:11px">${p.value[0]}</div><div style="font-size:11px;margin-top:2px">${p.value[1]} 次提交</div>`
      },
    },
    visualMap: {
      show: visiblePoints.length > 0, type: 'continuous', min: 0, max, right: 14, bottom: 4, orient: 'horizontal',
      calculable: true, precision: 2, itemWidth: 8, itemHeight: 105, text: ['多', '少'], textGap: 9,
      textStyle: { color: t.muted, fontSize: 9 },
      inRange: { color: t.heat },
      outOfRange: { color: t.dark ? '#46464e' : '#cbd1d7' },
    },
    calendar: {
      range: [start, end], left, top: 26,
      cellSize: [cellSize, cellSize], splitLine: { show: false },
      itemStyle: { color: t.dark ? '#34343b' : '#e5e9ed', borderColor: t.panel, borderWidth: 2 },
      dayLabel: { color: t.muted, fontSize: 9, nameMap: ['日', '一', '二', '三', '四', '五', '六'] },
      monthLabel: { show: true, color: t.ink, fontSize: 9.5, nameMap: 'cn' },
      yearLabel: { show: false },
    },
    series: [{
      type: 'heatmap', coordinateSystem: 'calendar',
      data: visiblePoints.map((point) => [point.date, point.value]),
      itemStyle: { borderRadius: 2, borderColor: t.panel, borderWidth: 2 },
    }],
  }
}
