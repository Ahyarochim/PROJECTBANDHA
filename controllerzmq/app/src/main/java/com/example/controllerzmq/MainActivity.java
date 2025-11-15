package com.example.controllerzmq;

import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.TextView;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;
import androidx.core.content.ContextCompat;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowInsetsCompat;

import org.zeromq.SocketType;
import org.zeromq.ZContext;
import org.zeromq.ZMQ;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class MainActivity extends AppCompatActivity {

    private static final String TAG = "ControllerZMQ";

    private EditText etIpAddress, etPort, etMessage;
    private Button btnConnect, btnSend;
    private TextView tvStatus;

    private ExecutorService executorService;
    private Handler mainHandler;

    private ZContext context;
    private ZMQ.Socket socket;
    private boolean isConnected = false;
    private boolean isSending = false;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        setupSystemInsets();
        initViews();
        initExecutor();
        setupClickListeners();
        addWelcomeLog();
    }

    private void setupSystemInsets() {
        View rootView = findViewById(android.R.id.content);

        ViewCompat.setOnApplyWindowInsetsListener(rootView, (v, insets) -> {
            int topInset = insets.getInsets(WindowInsetsCompat.Type.systemBars()).top;
            int bottomInset = insets.getInsets(WindowInsetsCompat.Type.systemBars()).bottom;

            v.setPadding(
                    v.getPaddingLeft(),
                    Math.max(v.getPaddingTop(), topInset),
                    v.getPaddingRight(),
                    Math.max(v.getPaddingBottom(), bottomInset));

            return WindowInsetsCompat.CONSUMED;
        });
    }

    private void initViews() {
        etIpAddress = findViewById(R.id.etIpAddress);
        etPort = findViewById(R.id.etPort);
        etMessage = findViewById(R.id.etMessage);
        btnConnect = findViewById(R.id.btnConnect);
        btnSend = findViewById(R.id.btnSend);
        tvStatus = findViewById(R.id.tvStatus);
    }

    private void initExecutor() {
        executorService = Executors.newSingleThreadExecutor();
        mainHandler = new Handler(Looper.getMainLooper());
    }

    private void setupClickListeners() {
        btnConnect.setOnClickListener(v -> {
            if (isConnected) {
                disconnect();
            } else {
                connect();
            }
        });

        btnSend.setOnClickListener(v -> sendMessage());
    }

    private void addWelcomeLog() {
        updateStatus("Ready to Connect", StatusType.READY);
    }

    private void connect() {
        String ipAddress = etIpAddress.getText().toString().trim();
        String portStr = etPort.getText().toString().trim();

        if (ipAddress.isEmpty()) {
            showToast("IP Address tidak boleh kosong");
            etIpAddress.requestFocus();
            return;
        }

        if (portStr.isEmpty()) {
            showToast("Port tidak boleh kosong");
            etPort.requestFocus();
            return;
        }

        int port;
        try {
            port = Integer.parseInt(portStr);
            if (port < 1 || port > 65535) {
                showToast("Port harus antara 1-65535");
                etPort.requestFocus();
                return;
            }
        } catch (NumberFormatException e) {
            showToast("Port harus berupa angka yang valid");
            etPort.requestFocus();
            return;
        }

        if (!isValidIP(ipAddress)) {
            showToast("Format IP Address tidak valid");
            etIpAddress.requestFocus();
            return;
        }

        updateStatus("Connecting...", StatusType.SENDING);
        btnConnect.setEnabled(false);
        setInputsEnabled(false);

        executorService.execute(() -> connectToServer(ipAddress, port));
    }

    private void connectToServer(String ipAddress, int port) {
        try {
            context = new ZContext();

            socket = context.createSocket(SocketType.PUSH);

            socket.setSendTimeOut(5000);
            socket.setLinger(1000);
            socket.setSndHWM(1000);

            String connectionString = "tcp://" + ipAddress + ":" + port;
            Log.d(TAG, "Attempting to connect to: " + connectionString);

            // Untuk ZeroMQ PUSH socket, connect() selalu return true
            // karena koneksi bersifat asynchronous
            socket.connect(connectionString);

            // Berikan waktu untuk establish connection
            Thread.sleep(500);

            isConnected = true;
            Log.d(TAG, "Connection established successfully");

            mainHandler.post(() -> {
                updateStatus("Connected", StatusType.SUCCESS);
                btnConnect.setText("DISCONNECT");
                btnConnect.setEnabled(true);
                setInputsEnabled(false);
                setSendButtonsEnabled(true);
                showToast("Koneksi berhasil!");
            });

        } catch (Exception e) {
            Log.e(TAG, "Error connecting", e);
            final String errorMsg = (e.getMessage() != null) ? e.getMessage() : "Unknown error";

            mainHandler.post(() -> {
                updateStatus("Connection Failed", StatusType.ERROR);
                btnConnect.setEnabled(true);
                setInputsEnabled(true);
                showToast("Gagal connect: " + errorMsg);
            });

            cleanup();
        }
    }

    private void disconnect() {
        updateStatus("Disconnecting...", StatusType.SENDING);
        btnConnect.setEnabled(false);
        setSendButtonsEnabled(false);

        executorService.execute(() -> {
            cleanup();

            mainHandler.post(() -> {
                isConnected = false;
                updateStatus("Disconnected", StatusType.READY);
                btnConnect.setText("CONNECT");
                btnConnect.setEnabled(true);
                setInputsEnabled(true);
                showToast("Disconnected");
            });
        });
    }

    private void cleanup() {
        try {
            if (socket != null) {
                socket.close();
                socket = null;
            }
            if (context != null) {
                context.close();
                context = null;
            }
        } catch (Exception e) {
            Log.e(TAG, "Error during cleanup", e);
        }
    }

    private void sendMessage() {
        if (!isConnected) {
            showToast("❌ Belum connected! Klik tombol CONNECT terlebih dahulu");
            return;
        }

        if (isSending) {
            showToast("Sedang mengirim data, harap tunggu...");
            return;
        }

        String message = etMessage.getText().toString();

        if (message.isEmpty()) {
            showToast("Pesan tidak boleh kosong");
            etMessage.requestFocus();
            return;
        }

        isSending = true;
        updateStatus("Sending...", StatusType.SENDING);
        setSendButtonsEnabled(false);

        executorService.execute(() -> sendZeroMQMessage(message));
    }

    private boolean isValidIP(String ip) {
        try {
            String[] parts = ip.split("\\.");
            if (parts.length != 4)
                return false;

            for (String part : parts) {
                int num = Integer.parseInt(part);
                if (num < 0 || num > 255)
                    return false;
            }
            return true;
        } catch (Exception e) {
            return false;
        }
    }

    private void sendZeroMQMessage(String message) {
        try {
            if (socket == null || !isConnected) {
                throw new RuntimeException("Socket tidak tersedia");
            }

            Log.d(TAG, "Sending message: " + message);
            boolean sent = socket.send(message.getBytes(ZMQ.CHARSET), 0);

            if (!sent) {
                throw new RuntimeException("Gagal mengirim pesan");
            }

            Log.d(TAG, "Message sent successfully");

            mainHandler.post(() -> {
                updateStatus("Connected", StatusType.SUCCESS);
                showToast("Data terkirim!");
            });

        } catch (Exception e) {
            Log.e(TAG, "Error sending message", e);
            final String errorMsg = (e.getMessage() != null) ? e.getMessage() : "Unknown error";

            mainHandler.post(() -> {
                updateStatus("Send Failed", StatusType.ERROR);
                showToast("Gagal mengirim: " + errorMsg);
            });

        } finally {
            mainHandler.post(() -> {
                isSending = false;
                setSendButtonsEnabled(true);
            });
        }
    }

    private void setInputsEnabled(boolean enabled) {
        etIpAddress.setEnabled(enabled);
        etPort.setEnabled(enabled);
    }

    private void setSendButtonsEnabled(boolean enabled) {
        btnSend.setEnabled(enabled);
        etMessage.setEnabled(enabled);
    }

    enum StatusType {
        READY, SENDING, SUCCESS, ERROR
    }

    private void updateStatus(String status, StatusType type) {
        mainHandler.post(() -> {
            tvStatus.setText(status);

            int backgroundRes;
            switch (type) {
                case SENDING:
                    backgroundRes = R.drawable.status_sending;
                    break;
                case SUCCESS:
                    backgroundRes = R.drawable.status_ready;
                    break;
                case ERROR:
                    backgroundRes = R.drawable.status_error;
                    break;
                default:
                    backgroundRes = R.drawable.status_ready;
                    break;
            }

            tvStatus.setBackground(ContextCompat.getDrawable(this, backgroundRes));
        });
    }

    private void showToast(String message) {
        mainHandler.post(() -> Toast.makeText(MainActivity.this, message, Toast.LENGTH_SHORT).show());
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();

        if (isConnected) {
            cleanup();
        }

        if (executorService != null && !executorService.isShutdown()) {
            executorService.shutdown();
        }

    }

    @Override
    protected void onResume() {
        super.onResume();
        if (!isConnected && !isSending) {
            updateStatus("Disconnected", StatusType.READY);
        }
    }
}
