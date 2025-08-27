import { getServiceUrl } from '../api';
import RequestService from '../httpRequest';

export default {
    // バインド済みデバイス
    getAgentBindDevices(agentId, callback) {
        RequestService.sendRequest()
            .url(`${getServiceUrl()}/device/bind/${agentId}`)
            .method('GET')
            .success((res) => {
                RequestService.clearRequestTime();
                callback(res);
            })
            .networkFail((err) => {
                console.error('デバイスリストの取得に失敗しました:', err);
                RequestService.reAjaxFun(() => {
                    this.getAgentBindDevices(agentId, callback);
                });
            }).send();
    },
    // デバイスのバインドを解除
    unbindDevice(device_id, callback) {
        RequestService.sendRequest()
            .url(`${getServiceUrl()}/device/unbind`)
            .method('POST')
            .data({ deviceId: device_id })
            .success((res) => {
                RequestService.clearRequestTime();
                callback(res);
            })
            .networkFail((err) => {
                console.error('デバイスのバインド解除に失敗しました:', err);
                RequestService.reAjaxFun(() => {
                    this.unbindDevice(device_id, callback);
                });
            }).send();
    },
    // デバイスをバインド
    bindDevice(agentId, deviceCode, callback) {
        RequestService.sendRequest()
            .url(`${getServiceUrl()}/device/bind/${agentId}/${deviceCode}`)
            .method('POST')
            .success((res) => {
                RequestService.clearRequestTime();
                callback(res);
            })
            .networkFail((err) => {
                console.error('デバイスのバインドに失敗しました:', err);
                RequestService.reAjaxFun(() => {
                    this.bindDevice(agentId, deviceCode, callback);
                });
            }).send();
    },
    updateDeviceInfo(id, payload, callback) {
        RequestService.sendRequest()
            .url(`${getServiceUrl()}/device/update/${id}`)
            .method('PUT')
            .data(payload)
            .success((res) => {
                RequestService.clearRequestTime()
                callback(res)
            })
            .networkFail((err) => {
                console.error('OTAステータスの更新に失敗しました:', err)
                this.$message.error(err.msg || 'OTAステータスの更新に失敗しました')
                RequestService.reAjaxFun(() => {
                    this.updateDeviceInfo(id, payload, callback)
                })
            }).send()
    },
    // デバイスを手動で追加
    manualAddDevice(params, callback) {
        RequestService.sendRequest()
            .url(`${getServiceUrl()}/device/manual-add`)
            .method('POST')
            .data(params)
            .success((res) => {
                RequestService.clearRequestTime();
                callback(res);
            })
            .networkFail((err) => {
                console.error('手動でのデバイス追加に失敗しました:', err);
                RequestService.reAjaxFun(() => {
                    this.manualAddDevice(params, callback);
                });
            }).send();
    },
}