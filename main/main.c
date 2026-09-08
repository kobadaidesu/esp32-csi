#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "nvs_flash.h"

static const char *TAG = "wifi_csi";

static void wifi_event_handler(void *arg, esp_event_base_t event_base,
                               int32_t event_id, void *event_data)
{
    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
        ESP_LOGI(TAG, "Connecting to Wi-Fi...");
        ESP_ERROR_CHECK(esp_wifi_connect());
    } else if (event_base == WIFI_EVENT &&
               event_id == WIFI_EVENT_STA_DISCONNECTED) {
        ESP_LOGW(TAG, "Disconnected. Reconnecting...");
        ESP_ERROR_CHECK(esp_wifi_connect());
    } else if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        const ip_event_got_ip_t *event = (const ip_event_got_ip_t *)event_data;

        ESP_LOGI(TAG, "Got IP: " IPSTR, IP2STR(&event->ip_info.ip));
    }
}

static void csi_rx_callback(void *ctx, wifi_csi_info_t *info)
{
    static unsigned long frame_count;

    if (info == NULL || info->buf == NULL) {
        return;
    }

    frame_count++;
    if (frame_count % CONFIG_CSI_PRINT_EVERY != 0) {
        return;
    }

    unsigned int print_len = info->len;
    if (print_len > CONFIG_CSI_PRINT_BYTES) {
        print_len = CONFIG_CSI_PRINT_BYTES;
    }

    printf("CSI: RSSI=%d len=%u first_word_invalid=%d data=[",
           info->rx_ctrl.rssi, (unsigned int)info->len,
           info->first_word_invalid);

    for (unsigned int i = 0; i < print_len; i++) {
        printf("%d", info->buf[i]);
        if (i + 1 < print_len) {
            putchar(',');
        }
    }

    puts("]");
}

static void wifi_init(void)
{
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());

    esp_netif_t *station = esp_netif_create_default_wifi_sta();
    if (station == NULL) {
        ESP_LOGE(TAG, "Failed to create the default Wi-Fi station");
        abort();
    }

    wifi_init_config_t init_config = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&init_config));

    ESP_ERROR_CHECK(esp_event_handler_register(
        WIFI_EVENT, ESP_EVENT_ANY_ID, wifi_event_handler, NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(
        IP_EVENT, IP_EVENT_STA_GOT_IP, wifi_event_handler, NULL));

    wifi_config_t wifi_config = {0};
    strlcpy((char *)wifi_config.sta.ssid, CONFIG_CSI_WIFI_SSID,
            sizeof(wifi_config.sta.ssid));
    strlcpy((char *)wifi_config.sta.password, CONFIG_CSI_WIFI_PASSWORD,
            sizeof(wifi_config.sta.password));

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi_config));
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_ERROR_CHECK(esp_wifi_set_ps(WIFI_PS_NONE));
}

static void csi_init(void)
{
    ESP_ERROR_CHECK(esp_wifi_set_promiscuous(true));

    const wifi_csi_config_t csi_config = {
        .lltf_en = true,
        .htltf_en = true,
        .stbc_htltf2_en = true,
        .ltf_merge_en = true,
        .channel_filter_en = true,
        .manu_scale = false,
        .shift = 0,
        .dump_ack_en = false,
    };

    ESP_ERROR_CHECK(esp_wifi_set_csi_config(&csi_config));
    ESP_ERROR_CHECK(esp_wifi_set_csi_rx_cb(csi_rx_callback, NULL));
    ESP_ERROR_CHECK(esp_wifi_set_csi(true));

    ESP_LOGI(TAG, "CSI enabled");
}

void app_main(void)
{
    esp_err_t result = nvs_flash_init();
    if (result == ESP_ERR_NVS_NO_FREE_PAGES ||
        result == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        result = nvs_flash_init();
    }
    ESP_ERROR_CHECK(result);

    if (strlen(CONFIG_CSI_WIFI_SSID) == 0) {
        ESP_LOGE(TAG, "Wi-Fi SSID is empty. Run 'idf.py menuconfig' first.");
        return;
    }

    wifi_init();
    csi_init();
}
