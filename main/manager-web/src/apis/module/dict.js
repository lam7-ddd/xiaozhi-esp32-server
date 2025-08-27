import { getServiceUrl } from '../api';
import RequestService from '../httpRequest';

export default {
    // 辞書タイプリストを取得
    getDictTypeList(params, callback) {
        const queryParams = new URLSearchParams({
            dictType: params.dictType || '',
            dictName: params.dictName || '',
            page: params.page || 1,
            limit: params.limit || 10
        }).toString();

        RequestService.sendRequest()
            .url(`${getServiceUrl()}/admin/dict/type/page?${queryParams}`)
            .method('GET')
            .success((res) => {
                RequestService.clearRequestTime()
                callback(res)
            })
            .networkFail((err) => {
                console.error('辞書タイプ一覧の取得に失敗しました:', err)
                this.$message.error(err.msg || '辞書タイプ一覧の取得に失敗しました')
                RequestService.reAjaxFun(() => {
                    this.getDictTypeList(params, callback)
                })
            }).send()
    },

    // 辞書タイプの詳細を取得
    getDictTypeDetail(id, callback) {
        RequestService.sendRequest()
            .url(`${getServiceUrl()}/admin/dict/type/${id}`)
            .method('GET')
            .success((res) => {
                RequestService.clearRequestTime()
                callback(res)
            })
            .networkFail((err) => {
                console.error('辞書タイプの詳細の取得に失敗しました:', err)
                this.$message.error(err.msg || '辞書タイプの詳細の取得に失敗しました')
                RequestService.reAjaxFun(() => {
                    this.getDictTypeDetail(id, callback)
                })
            }).send()
    },

    // 辞書タイプを新規追加
    addDictType(data, callback) {
        RequestService.sendRequest()
            .url(`${getServiceUrl()}/admin/dict/type/save`)
            .method('POST')
            .data(data)
            .success((res) => {
                RequestService.clearRequestTime()
                callback(res)
            })
            .networkFail((err) => {
                console.error('辞書タイプの追加に失敗しました:', err)
                this.$message.error(err.msg || '辞書タイプの追加に失敗しました')
                RequestService.reAjaxFun(() => {
                    this.addDictType(data, callback)
                })
            }).send()
    },

    // 辞書タイプを更新
    updateDictType(data, callback) {
        RequestService.sendRequest()
            .url(`${getServiceUrl()}/admin/dict/type/update`)
            .method('PUT')
            .data(data)
            .success((res) => {
                RequestService.clearRequestTime()
                callback(res)
            })
            .networkFail((err) => {
                console.error('辞書タイプの更新に失敗しました:', err)
                this.$message.error(err.msg || '辞書タイプの更新に失敗しました')
                RequestService.reAjaxFun(() => {
                    this.updateDictType(data, callback)
                })
            }).send()
    },

    // 辞書タイプを削除
    deleteDictType(ids, callback) {
        RequestService.sendRequest()
            .url(`${getServiceUrl()}/admin/dict/type/delete`)
            .method('POST')
            .data(ids)
            .success((res) => {
                RequestService.clearRequestTime()
                callback(res)
            })
            .networkFail((err) => {
                console.error('辞書タイプの削除に失敗しました:', err)
                this.$message.error(err.msg || '辞書タイプの削除に失敗しました')
                RequestService.reAjaxFun(() => {
                    this.deleteDictType(ids, callback)
                })
            }).send()
    },

    // 辞書データリストを取得
    getDictDataList(params, callback) {
        const queryParams = new URLSearchParams({
            dictTypeId: params.dictTypeId,
            dictLabel: params.dictLabel || '',
            dictValue: params.dictValue || '',
            page: params.page || 1,
            limit: params.limit || 10
        }).toString();

        RequestService.sendRequest()
            .url(`${getServiceUrl()}/admin/dict/data/page?${queryParams}`)
            .method('GET')
            .success((res) => {
                RequestService.clearRequestTime()
                callback(res)
            })
            .networkFail((err) => {
                console.error('辞書データ一覧の取得に失敗しました:', err)
                this.$message.error(err.msg || '辞書データ一覧の取得に失敗しました')
                RequestService.reAjaxFun(() => {
                    this.getDictDataList(params, callback)
                })
            }).send()
    },

    // 辞書データの詳細を取得
    getDictDataDetail(id, callback) {
        RequestService.sendRequest()
            .url(`${getServiceUrl()}/admin/dict/data/${id}`)
            .method('GET')
            .success((res) => {
                RequestService.clearRequestTime()
                callback(res)
            })
            .networkFail((err) => {
                console.error('辞書データの詳細の取得に失敗しました:', err)
                this.$message.error(err.msg || '辞書データの詳細の取得に失敗しました')
                RequestService.reAjaxFun(() => {
                    this.getDictDataDetail(id, callback)
                })
            }).send()
    },

    // 辞書データを新規追加
    addDictData(data, callback) {
        RequestService.sendRequest()
            .url(`${getServiceUrl()}/admin/dict/data/save`)
            .method('POST')
            .data(data)
            .success((res) => {
                RequestService.clearRequestTime()
                callback(res)
            })
            .networkFail((err) => {
                console.error('辞書データの追加に失敗しました:', err)
                this.$message.error(err.msg || '辞書データの追加に失敗しました')
                RequestService.reAjaxFun(() => {
                    this.addDictData(data, callback)
                })
            }).send()
    },

    // 辞書データを更新
    updateDictData(data, callback) {
        RequestService.sendRequest()
            .url(`${getServiceUrl()}/admin/dict/data/update`)
            .method('PUT')
            .data(data)
            .success((res) => {
                RequestService.clearRequestTime()
                callback(res)
            })
            .networkFail((err) => {
                console.error('辞書データの更新に失敗しました:', err)
                this.$message.error(err.msg || '辞書データの更新に失敗しました')
                RequestService.reAjaxFun(() => {
                    this.updateDictData(data, callback)
                })
            }).send()
    },

    // 辞書データを削除
    deleteDictData(ids, callback) {
        RequestService.sendRequest()
            .url(`${getServiceUrl()}/admin/dict/data/delete`)
            .method('POST')
            .data(ids)
            .success((res) => {
                RequestService.clearRequestTime()
                callback(res)
            })
            .networkFail((err) => {
                console.error('辞書データの削除に失敗しました:', err)
                this.$message.error(err.msg || '辞書データの削除に失敗しました')
                RequestService.reAjaxFun(() => {
                    this.deleteDictData(ids, callback)
                })
            }).send()
    },

    // 辞書データリストを取得
    getDictDataByType(dictType) {
        return new Promise((resolve, reject) => {
            RequestService.sendRequest()
                .url(`${getServiceUrl()}/admin/dict/data/type/${dictType}`)
                .method('GET')
                .success((res) => {
                    RequestService.clearRequestTime()
                    if (res.data && res.data.code === 0) {
                        resolve(res.data)
                    } else {
                        reject(new Error(res.data?.msg || '辞書データ一覧の取得に失敗しました'))
                    }
                })
                .networkFail((err) => {
                    console.error('辞書データ一覧の取得に失敗しました:', err)
                    reject(err)
                }).send()
        })
    }

} 