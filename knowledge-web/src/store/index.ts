import { PiniaVuePlugin, createPinia } from "pinia"
import piniaLocalStorage from "pinia-plugin-persistedstate"
import Vue from "vue"

Vue.use(PiniaVuePlugin)

const pinia = createPinia()
pinia.use(piniaLocalStorage)

export default pinia
