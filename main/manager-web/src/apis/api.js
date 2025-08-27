// 各モジュールのリクエストをインポート
import admin from './module/admin.js'
import agent from './module/agent.js'
import device from './module/device.js'
import dict from './module/dict.js'
import model from './module/model.js'
import ota from './module/ota.js'
import timbre from "./module/timbre.js"
import user from './module/user.js'

/**
 * APIアドレス
 * 開発時は.env.developmentファイルを自動的に読み込んで使用します
 * ビルド時は.env.productionファイルを自動的に読み込んで使用します
 */
const DEV_API_SERVICE = process.env.VUE_APP_API_BASE_URL

/**
 * 開発環境に応じてAPIのURLを返します
 * @returns {string}
 */
export function getServiceUrl() {
    return DEV_API_SERVICE
}

/** requestサービスのカプセル化 */
export default {
    getServiceUrl,
    user,
    admin,
    agent,
    device,
    model,
    timbre,
    ota,
    dict
}
