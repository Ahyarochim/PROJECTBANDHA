package com.example.controllerzmq;

import android.content.SharedPreferences;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ImageButton;
import android.widget.TextView;
import android.widget.Toast;
import android.widget.ImageView;

import androidx.activity.EdgeToEdge;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.graphics.Insets;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowInsetsCompat;

import org.zeromq.SocketType;
import org.zeromq.ZContext;
import org.zeromq.ZMQ;

public class MainActivity extends AppCompatActivity {

    private UDPReceiver receiver;
    private ImageView videoStream;
    private Button btnConnect, btnAuto;
    private ImageButton btnSetting, btnRotateRight, btnRotateLeft;
    private TextView koor;
    private String msg;
    private JoystickView joystick;
    private TextView petunjuk;

    private float valX = 0f, valY = 0f, valRotation = 0f;

    private Handler handler = new Handler(Looper.getMainLooper());

    private ZContext context;
    private ZMQ.Socket socket; // Socket PUSH untuk kirim joystick data
    private ZContext visionContext;
    private ZMQ.Socket visionSocket; // Socket PULL untuk terima sinyal vision
    private boolean isConnected = false;
    private boolean visionSignal = false; // Status sinyal dari vision
    private Thread visionListenerThread;

    private String serverIp = "10.107.137.167";
    private int serverPort = 6000; // Port untuk kirim joystick data
    private int visionPort = 6001; // Port untuk terima sinyal vision

    private SharedPreferences prefs;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        EdgeToEdge.enable(this);
        setContentView(R.layout.activity_controller);

        videoStream = findViewById(R.id.videoStream);

        // MULAI RECEIVER
        receiver = new UDPReceiver(6000, bmp -> runOnUiThread(() -> {
            videoStream.setImageBitmap(bmp);
        }));
        receiver.start();

        setupSystemInsets();

        prefs = getSharedPreferences("ZMQ_PREFS", MODE_PRIVATE);
        serverIp = prefs.getString("IP", serverIp);
        serverPort = prefs.getInt("PORT", serverPort);
        visionPort = prefs.getInt("VISION_PORT", visionPort);

        // init views
        btnConnect = findViewById(R.id.btnConnect);
        btnSetting = findViewById(R.id.btnSetting);
        koor = findViewById(R.id.koord);
        joystick = findViewById(R.id.joystick);
        petunjuk = findViewById(R.id.valJoy);
        btnRotateRight = findViewById(R.id.btnRotateRight);
        btnRotateLeft = findViewById(R.id.btnRotateLeft);
        btnAuto = findViewById(R.id.btnAuto);

        // Disable btnAuto initially
        btnAuto.setEnabled(false);
        btnAuto.setAlpha(0.5f); // Visual indicator bahwa button disabled

        // connect/disconnect button
        btnConnect.setOnClickListener(v -> {
            if (!isConnected) connectToServer();
            else disconnectFromServer();
        });

        // settings button
        btnSetting.setOnClickListener(v -> showIpPortDialog());

        // btnAuto listener
        btnAuto.setOnClickListener(v -> {
            if (visionSignal) {
                Toast.makeText(this, "Auto mode activated!", Toast.LENGTH_SHORT).show();
                // Tambahkan logic auto mode kamu di sini
                // Misal: kirim perintah khusus ke server
                sendAutoCommand();
            }
        });

        // automatic connect
        handler.postDelayed(() -> {
            if (!isConnected) connectToServer();
            startVisionListener(); // Mulai listen sinyal vision
        }, 500);

        // Setup joystick listener
        joystick.setJoystickListener(new JoystickView.JoystickListener() {
            @Override
            public void onJoystickMoved(float xPercent, float yPercent, int direction) {
                valX = xPercent * 90;
                valY = yPercent * 90;

                updateCoordinateDisplay();

                if (isConnected) {
                    sendCoordinate(valX, valY);
                }

                String dirText = getDirectionText(direction);
                petunjuk.setText(String.format("X: %.2f | Y: %.2f\n%s",
                        xPercent, yPercent, dirText));
            }
        });
    }

    private void startVisionListener() {
        visionListenerThread = new Thread(() -> {
            try {
                visionContext = new ZContext();
                visionSocket = visionContext.createSocket(SocketType.PULL);
                visionSocket.setReceiveTimeOut(100); // Timeout 100ms biar bisa check interrupt
                visionSocket.bind("tcp://*:" + visionPort);

                Log.d("ZMQ_VISION", "Vision listener started, binding to port " + visionPort);

                runOnUiThread(() ->
                        Toast.makeText(this, "Vision listener ready", Toast.LENGTH_SHORT).show()
                );

                while (!Thread.currentThread().isInterrupted()) {
                    try {
                        String signal = visionSocket.recvStr();
                        if (signal != null && !signal.isEmpty()) {
                            Log.d("ZMQ_VISION", "Received signal: " + signal);

                            // Check if signal is "1"
                            boolean newSignal = signal.trim().equals("1");

                            // Update hanya kalau ada perubahan
                            if (newSignal != visionSignal) {
                                visionSignal = newSignal;
                                runOnUiThread(() -> updateAutoButtonState());
                            }
                        }
                    } catch (Exception e) {
                        // Timeout atau error lain, continue loop
                        if (Thread.currentThread().isInterrupted()) {
                            break;
                        }
                    }
                }

                Log.d("ZMQ_VISION", "Vision listener stopped");

            } catch (Exception e) {
                Log.e("ZMQ_VISION", "Vision listener error", e);
                runOnUiThread(() ->
                        Toast.makeText(this, "Vision listener error", Toast.LENGTH_SHORT).show()
                );
            }
        });
        visionListenerThread.start();
    }

    private void updateAutoButtonState() {
        btnAuto.setEnabled(visionSignal);
        btnAuto.setAlpha(visionSignal ? 1.0f : 0.5f);

        String status = visionSignal ? "available ✓" : "unavailable ✗";
        Log.d("ZMQ_VISION", "Auto mode " + status);

        // Optional: tampilkan toast
        // Toast.makeText(this, "Auto mode " + status, Toast.LENGTH_SHORT).show();
    }

    private void sendAutoCommand() {
        if (socket != null && isConnected) {
            String msg = "AUTO_START"; // Atau command lain sesuai kebutuhan
            socket.send(msg.getBytes(ZMQ.CHARSET));
            Log.d("ZMQ", "Sent auto command: " + msg);
        }
    }

    private String getDirectionText(int direction) {
        switch (direction) {
            case 0: return "CENTER ●";
            case 1: return "ATAS ↑";
            case 2: return "KANAN ATAS ↗";
            case 3: return "KANAN →";
            case 4: return "KANAN BAWAH ↘";
            case 5: return "BAWAH ↓";
            case 6: return "KIRI BAWAH ↙";
            case 7: return "KIRI ←";
            case 8: return "KIRI ATAS ↖";
            default: return "???";
        }
    }

    private void setupSystemInsets() {
        View rootView = findViewById(android.R.id.content);
        ViewCompat.setOnApplyWindowInsetsListener(rootView, (v, insets) -> {
            Insets systemBars = insets.getInsets(WindowInsetsCompat.Type.systemBars());
            v.setPadding(systemBars.left, systemBars.top, systemBars.right, systemBars.bottom);
            return WindowInsetsCompat.CONSUMED;
        });
    }

    private void updateCoordinateDisplay() {
        koor.setText(String.format("(%.2f, %.2f)", valX, valY));
    }

    private void resetCoordinates() {
        valX = 0f;
        valY = 0f;
        updateCoordinateDisplay();

        if (isConnected) sendCoordinate(valX, valY);
    }

    private void showIpPortDialog() {
        View dialogView = getLayoutInflater().inflate(R.layout.dialog_ip_port, null);
        EditText etIp = dialogView.findViewById(R.id.etIpAddress);
        EditText etPort = dialogView.findViewById(R.id.etPort);
        etIp.setText(serverIp);
        etPort.setText(String.valueOf(serverPort));

        new androidx.appcompat.app.AlertDialog.Builder(this)
                .setTitle("Server Settings")
                .setView(dialogView)
                .setPositiveButton("Connect", (dialog, which) -> {
                    String ip = etIp.getText().toString().trim();
                    String portStr = etPort.getText().toString().trim();
                    if (ip.isEmpty() || portStr.isEmpty()) {
                        Toast.makeText(this, "IP and Port cannot be empty", Toast.LENGTH_SHORT).show();
                        return;
                    }
                    int port;
                    try {
                        port = Integer.parseInt(portStr);
                    } catch (NumberFormatException e) {
                        Toast.makeText(this, "Port must be a number", Toast.LENGTH_SHORT).show();
                        return;
                    }

                    serverIp = ip;
                    serverPort = port;

                    // Save preferences
                    prefs.edit()
                            .putString("IP", serverIp)
                            .putInt("PORT", serverPort)
                            .putInt("VISION_PORT", visionPort)
                            .apply();

                    disconnectFromServer();
                    connectToServer();
                })
                .setNegativeButton("Cancel", null)
                .show();
    }

    private void connectToServer() {
        new Thread(() -> {
            try {
                context = new ZContext();
                socket = context.createSocket(SocketType.PUSH);
                socket.setSendTimeOut(1000);
                socket.setLinger(500);
                socket.connect("tcp://" + serverIp + ":" + serverPort);
                isConnected = true;

                Log.d("ZMQ", "Connected to " + serverIp + ":" + serverPort);

                runOnUiThread(() -> {
                    btnConnect.setText("DISCONNECT");
                    Toast.makeText(this, "Connected to server", Toast.LENGTH_SHORT).show();
                });
            } catch (Exception e) {
                Log.e("ZMQ", "Connection failed", e);
                runOnUiThread(() ->
                        Toast.makeText(this, "Connection failed: " + e.getMessage(), Toast.LENGTH_SHORT).show()
                );
            }
        }).start();
    }

    private void sendCoordinate(float x, float y) {
        if (socket != null && isConnected) {
            String msg = x + "," + y;
            socket.send(msg.getBytes(ZMQ.CHARSET));
            Log.d("ZMQ", "Sent: " + msg);
        }
    }

    private void disconnectFromServer() {
        new Thread(() -> {
            try {
                resetCoordinates();

                // Close joystick socket
                if (socket != null) {
                    socket.close();
                    socket = null;
                }
                if (context != null) {
                    context.close();
                    context = null;
                }

                // Stop vision listener thread
                if (visionListenerThread != null && visionListenerThread.isAlive()) {
                    visionListenerThread.interrupt();
                    visionListenerThread.join(1000); // Wait max 1 second
                }

                // Close vision socket
                if (visionSocket != null) {
                    visionSocket.close();
                    visionSocket = null;
                }
                if (visionContext != null) {
                    visionContext.close();
                    visionContext = null;
                }

                isConnected = false;
                visionSignal = false;

                Log.d("ZMQ", "Disconnected from server");

                runOnUiThread(() -> {
                    btnConnect.setText("CONNECT");
                    updateAutoButtonState();
                    Toast.makeText(this, "Disconnected", Toast.LENGTH_SHORT).show();
                });
            } catch (Exception e) {
                Log.e("ZMQ", "Disconnect failed", e);
            }
        }).start();
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        disconnectFromServer();
        resetCoordinates();
        if (receiver != null) receiver.stopReceiver();
    }
}