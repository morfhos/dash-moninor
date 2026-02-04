<template>
  <svg class="donut" viewBox="0 0 42 42" xmlns="http://www.w3.org/2000/svg" :aria-label="title">
    <circle cx="21" cy="21" r="15.915" fill="transparent" stroke="#f1f5f9" stroke-width="8"></circle>
    
    <template v-for="(s, i) in segments" :key="i">
      <circle
        cx="21" cy="21" r="15.915"
        fill="transparent"
        :stroke="s.color"
        stroke-width="8"
        :stroke-dasharray="`${s.value} ${100 - s.value}`"
        :stroke-dashoffset="offsetFromIndex(i)"
      />
      
      <text
        v-if="s.value > 5"
        :x="labelPos(i).x"
        :y="labelPos(i).y"
        fill="white"
        font-size="3"
        font-weight="700"
        text-anchor="middle"
        dominant-baseline="middle"
      >
        {{ s.value }}%
      </text>
    </template>

    <text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" font-size="2.5" fill="#4c1d95" font-weight="700">
      <template v-if="centerText.includes('+')">
        <tspan x="50%" dy="-1.5">{{ centerText.split('+')[0].trim() }} +</tspan>
        <tspan x="50%" dy="3">{{ centerText.split('+')[1].trim() }}</tspan>
      </template>
      <template v-else>
        {{ centerText }}
      </template>
    </text>
  </svg>
</template>

<script>
export default {
  name: 'DonutChart',
  props: {
    title: { type: String, default: 'Investimento por Região' },
    segments: { type: Array, default: () => [] },
    centerText: { type: String, default: '' }
  },
  methods: {
    offsetFromIndex(i) {
      const prev = this.segments.slice(0, i).reduce((a, b) => a + b.value, 0)
      return 25 - prev
    },
    labelPos(i) {
      const prev = this.segments.slice(0, i).reduce((a, b) => a + b.value, 0)
      const current = this.segments[i].value
      const middle = prev + current / 2
      
      const angle = (middle / 100) * 2 * Math.PI - Math.PI / 2
      const r = 15.915
      
      return {
        x: 21 + Math.cos(angle) * r,
        y: 21 + Math.sin(angle) * r
      }
    }
  }
}
</script>

<style scoped>
.donut {
  width: 100%;
  height: auto;
  max-width: 280px;
  display: block;
  margin: 0 auto;
}
</style>
