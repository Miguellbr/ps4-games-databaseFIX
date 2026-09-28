package com.miguellbr.ps4gamesdatabase;

import android.os.Bundle;
import android.webkit.JavascriptInterface;
import android.webkit.WebView;
import androidx.annotation.Nullable;
import com.getcapacitor.BridgeActivity;
import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import org.json.JSONArray;
import org.json.JSONObject;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(@Nullable Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        WebView webView = getBridge().getWebView();
        webView.getSettings().setJavaScriptEnabled(true);
        webView.addJavascriptInterface(new DpiBridge(), "AndroidDPI");
    }

    public static class DpiBridge {
        @JavascriptInterface
        public String sendRpi(String psIp, String pkgUrl) {
            try {
                String normalized = pkgUrl.replace("https://", "http://");
                String encoded = URLEncoder.encode(normalized, StandardCharsets.UTF_8.name());
                JSONObject body = new JSONObject();
                body.put("type", "direct");
                JSONArray packages = new JSONArray();
                packages.put(encoded);
                body.put("packages", packages);
                return postJson("http://" + psIp + ":12800/api/install", body.toString());
            } catch (Exception e) {
                return error(e);
            }
        }

        @JavascriptInterface
        public String sendEtaHen(String psIp, String pkgUrl) {
            HttpURLConnection connection = null;
            try {
                String boundary = "----PS4DB-" + UUID.randomUUID().toString().replace("-", "");
                connection = (HttpURLConnection) new URL("http://" + psIp + ":12800/upload").openConnection();
                connection.setRequestMethod("POST");
                connection.setDoOutput(true);
                connection.setConnectTimeout(7000);
                connection.setReadTimeout(15000);
                connection.setRequestProperty("Content-Type", "multipart/form-data; boundary=" + boundary);

                String body = "--" + boundary + "\r\n"
                    + "Content-Disposition: form-data; name=\"file\"; filename=\"\"\r\n"
                    + "Content-Type: application/octet-stream\r\n\r\n\r\n"
                    + "--" + boundary + "\r\n"
                    + "Content-Disposition: form-data; name=\"url\"\r\n\r\n"
                    + pkgUrl + "\r\n"
                    + "--" + boundary + "--\r\n";
                try (OutputStream out = connection.getOutputStream()) {
                    out.write(body.getBytes(StandardCharsets.UTF_8));
                }
                return readResponse(connection);
            } catch (Exception e) {
                return error(e);
            } finally {
                if (connection != null) connection.disconnect();
            }
        }

        private static String postJson(String endpoint, String body) throws Exception {
            HttpURLConnection connection = (HttpURLConnection) new URL(endpoint).openConnection();
            try {
                connection.setRequestMethod("POST");
                connection.setDoOutput(true);
                connection.setConnectTimeout(7000);
                connection.setReadTimeout(15000);
                connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
                try (OutputStream out = connection.getOutputStream()) {
                    out.write(body.getBytes(StandardCharsets.UTF_8));
                }
                return readResponse(connection);
            } finally {
                connection.disconnect();
            }
        }

        private static String readResponse(HttpURLConnection connection) throws Exception {
            int status = connection.getResponseCode();
            InputStream stream = status >= 400 ? connection.getErrorStream() : connection.getInputStream();
            if (stream == null) return "{\"ok\":false,\"status\":" + status + "}";
            StringBuilder result = new StringBuilder();
            try (BufferedReader reader = new BufferedReader(new InputStreamReader(stream, StandardCharsets.UTF_8))) {
                String line;
                while ((line = reader.readLine()) != null) result.append(line);
            }
            JSONObject out = new JSONObject();
            out.put("ok", status >= 200 && status < 300);
            out.put("status", status);
            out.put("response", result.toString());
            return out.toString();
        }

        private static String error(Exception e) {
            try {
                JSONObject out = new JSONObject();
                out.put("ok", false);
                out.put("error", e.getClass().getSimpleName() + ": " + String.valueOf(e.getMessage()));
                return out.toString();
            } catch (Exception ignored) {
                return "{\"ok\":false,\"error\":\"Unknown error\"}";
            }
        }
    }
}
