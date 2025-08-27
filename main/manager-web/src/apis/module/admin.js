import { getServiceUrl } from '../api';
import RequestService from '../httpRequest';


export default {
    // ユーザーリスト
    getUserList(params, callback) {
        const queryParams = new URLSearchParams({
            page: params.page,
            limit: params.limit,
            mobile: params.mobile
        }).toString();

        RequestService.sendRequest()
            .url(`${getServiceUrl()}/admin/users?${queryParams}`)
            .method('GET')
            .success((res) => {
                RequestService.clearRequestTime()
                callback(res)
            })
            .networkFail((err) => {
                console.error('リクエスト失敗:', err)
                RequestService.reAjaxFun(() => {
                    this.getUserList(callback)
                })
            }).send()
    },
    // ユーザーを削除
    deleteUser(id, callback) {
        RequestService.sendRequest()
            .url(`${getServiceUrl()}/admin/users/${id}`)
            .method('DELETE')
            .success((res) => {
                RequestService.clearRequestTime()
                callback(res)
            })
            .networkFail((err) => {
                console.error('削除失敗:', err)
                RequestService.reAjaxFun(() => {
                    this.deleteUser(id, callback)
                })
            }).send()
    },
    // ユーザーパスワードをリセット
    resetUserPassword(id, callback) {
        RequestService.sendRequest()
            .url(`${getServiceUrl()}/admin/users/${id}`)
            .method('PUT')
            .success((res) => {
                RequestService.clearRequestTime()
                callback(res)
            })
            .networkFail((err) => {
                console.error('パスワードリセット失敗:', err)
                RequestService.reAjaxFun(() => {
                    this.resetUserPassword(id, callback)
                })
            }).send()
    },
    // パラメータリストを取得
    getParamsList(params, callback) {
        const queryParams = new URLSearchParams({
            page: params.page,
            limit: params.limit,
            paramCode: params.paramCode || ''
        }).toString();

        RequestService.sendRequest()
            .url(`${getServiceUrl()}/admin/params/page?${queryParams}`)
            .method('GET')
            .success((res) => {
                RequestService.clearRequestTime()
                callback(res)
            })
            .networkFail((err) => {
                console.error('パラメータリスト取得失敗:', err)
                RequestService.reAjaxFun(() => {
                    this.getParamsList(params, callback)
                })
            }).send()
    },
    // 保存
    addParam(data, callback) {
        RequestService.sendRequest()
            .url(`${getServiceUrl()}/admin/params`)
            .method('POST')
            .data(data)
            .success((res) => {
                RequestService.clearRequestTime()
                callback(res)
            })
            .networkFail((err) => {
                console.error('パラメータ追加失敗:', err)
                RequestService.reAjaxFun(() => {
                    this.addParam(data, callback)
                })
            }).send()
    },
    // 変更
    updateParam(data, callback) {
        RequestService.sendRequest()
            .url(`${getServiceUrl()}/admin/params`)
            .method('PUT')
            .data(data)
            .success((res) => {
                RequestService.clearRequestTime()
                callback(res)
            })
            .networkFail((err) => {
                console.error('パラメータ更新失敗:', err)
                RequestService.reAjaxFun(() => {
                    this.updateParam(data, callback)
                })
            }).send()
    },
    // 削除
    deleteParam(ids, callback) {
        RequestService.sendRequest()
            .url(`${getServiceUrl()}/admin/params/delete`)
            .method('POST')
            .data(ids)
            .success((res) => {
                RequestService.clearRequestTime()
                callback(res);
            })
            .networkFail((err) => {
                console.error('パラメータ削除失敗:', err)
                RequestService.reAjaxFun(() => {
                    this.deleteParam(ids, callback)
                })
            }).send()
    },
    // wsサーバーリストを取得
    getWsServerList(params, callback) {
        RequestService.sendRequest()
            .url(`${getServiceUrl()}/admin/server/server-list`)
            .method('GET')
            .success((res) => {
                RequestService.clearRequestTime()
                callback(res)
            })
            .networkFail((err) => {
                console.error('wsサーバーリスト取得失敗:', err)
                RequestService.reAjaxFun(() => {
                    this.getWsServerList(params, callback)
                })
            }).send();
    },
    // wsサーバーアクションコマンドを送信
    sendWsServerAction(data, callback) {
        RequestService.sendRequest()
            .url(`${getServiceUrl()}/admin/server/emit-action`)
            .method('POST')
            .data(data)
            .success((res) => {
                RequestService.clearRequestTime()
                callback(res)
            })
            .networkFail((err) => {
                RequestService.reAjaxFun(() => {
                    this.sendWsServerAction(data, callback)
                })
            }).send();
    }

}
