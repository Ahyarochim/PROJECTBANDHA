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
import com.google.android.material.slider.Slider;

import androidx.activity.EdgeToEdge;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.graphics.Insets;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowInsetsCompat;

import com.google.android.material.switchmaterial.SwitchMaterial;

import org.zeromq.SocketType;
import org.zeromq.ZContext;
import org.zeromq.ZMQ;

public class MainActivity extends AppCompatActivity {

    private UDPReceiver receiver;
    private ImageView videoStream;
    private Button btnConnect;
    private ImageButton btnSetting, btnRotateRight, btnRotateLeft;
    private TextView koor, tvGripper1Value, tvGripper2Value, tvGripper3Value;
    private String msg;
    private JoystickView joystick;
    private TextView petunjuk;
    private SwitchMaterial modeSwitch;
    private TextView modeStatusText;
    private Slider gripper1, gripper2, gripper3;

    private float valX = 0f, valY = 0f, valRotation = 0f, valA = 0f, valB = 0f, valC = 0f;

    private Handler handler = new Handler(Looper.getMainLooper());

    private ZContext context;
    private ZMQ.Socket socket; // Socket PUSH untuk kirim joystick data

    private boolean isConnected = false;
    private boolean isManualMode = true; // Default: Manual Mode

    private String serverIp = "10.107.137.167";
    private int serverPort = 6000; // Port untuk kirim joystick data

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

        // init views
        btnConnect = findViewById(R.id.btnConnect);
        btnSetting = findViewById(R.id.btnSetting);
        koor = findViewById(R.id.koord);
        joystick = findViewById(R.id.joystick);
        petunjuk = findViewById(R.id.valJoy);
        btnRotateRight = findViewById(R.id.btnRotateRight);
        btnRotateLeft = findViewById(R.id.btnRotateLeft);
        modeSwitch = findViewById(R.id.modeSwitch);
        modeStatusText = findViewById(R.id.modeStatusText);

        gripper1 = findViewById(R.id.gripper);
        gripper2 = findViewById(R.id.gripper2);
        gripper3 = findViewById(R.id.gripper3);

        tvGripper1Value = findViewById(R.id.tvGripper1Value);
        tvGripper2Value = findViewById(R.id.tvGripper2Value);
        tvGripper3Value = findViewById(R.id.tvGripper3Value);

        setupSliderListeners();

        // Setup mode switch listener
        modeSwitch.setOnCheckedChangeListener((buttonView, isChecked) -> {
            isManualMode = isChecked;
            updateModeDisplay();

            if (isConnected) {
                if (isManualMode) {
                    // Switching to Manual Mode
                    sendModeCommand("MANUAL");
                    Toast.makeText(this, "Switched to Manual Mode", Toast.LENGTH_SHORT).show();
                } else {
                    // Switching to Autonomous Mode
                    sendModeCommand("AUTO");
                    Toast.makeText(this, "Switched to Autonomous Mode", Toast.LENGTH_SHORT).show();
                }
            }
        });

        // connect/disconnect button
        btnConnect.setOnClickListener(v -> {
            if (!isConnected) connectToServer();
            else disconnectFromServer();
        });

        // settings button
        btnSetting.setOnClickListener(v -> showIpPortDialog());

        // Setup joystick listener
        joystick.setJoystickListener(new JoystickView.JoystickListener() {
            @Override
            public void onJoystickMoved(float xPercent, float yPercent, int direction) {
                valX = xPercent;
                valY = yPercent;

                updateCoordinateDisplay();

                // Only send coordinates in Manual Mode
                if (isConnected && isManualMode) {
                    sendCoordinate(valX, valY);
                }

                String dirText = getDirectionText(direction);
                petunjuk.setText(String.format("X: %.2f | Y: %.2f\n%s",
                        xPercent, yPercent, dirText));
            }
        });

        // Initial mode display
        updateModeDisplay();
    }

    private void setupSliderListeners() {
        // Gripper 1 listener
        gripper1.addOnChangeListener((slider, value, fromUser) -> {
            valA = value;
            tvGripper1Value.setText(String.format("Gripper 1: %.2f", valA));

            // Send slider data if connected and in manual mode
            if (isConnected && isManualMode) {
                sendSliderData();
            }
        });

        // Gripper 2 listener
        gripper2.addOnChangeListener((slider, value, fromUser) -> {
            valB = value;
            tvGripper2Value.setText(String.format("Gripper 2: %.2f", valB));

            if (isConnected && isManualMode) {
                sendSliderData();
            }
        });

        // Gripper 3 listener
        gripper3.addOnChangeListener((slider, value, fromUser) -> {
            valC = value;
            tvGripper3Value.setText(String.format("Gripper 3: %.2f", valC));

            if (isConnected && isManualMode) {
                sendSliderData();
            }
        });
    }

    private void sendSliderData() {
        if (socket != null && isConnected && isManualMode) {
            // Format: abc,value1,value2,value3
            String msg = String.format("abc,%.2f,%.2f,%.2f", valA, valB, valC);
            socket.send(msg.getBytes(ZMQ.CHARSET));
            Log.d("ZMQ", "Sent slider data: " + msg);
        }
    }

    private void resetSliders() {
        valA = 0f;
        valB = 0f;
        valC = 0f;

        gripper1.setValue(0f);
        gripper2.setValue(0f);
        gripper3.setValue(0f);

        tvGripper1Value.setText("Gripper 1: 0.00");
        tvGripper2Value.setText("Gripper 2: 0.00");
        tvGripper3Value.setText("Gripper 3: 0.00");

        if (isConnected && isManualMode) {
            sendSliderData();
        }
    }



    private void updateModeDisplay() {
        if (isManualMode) {
            modeStatusText.setText("Mode: MANUAL");
            modeStatusText.setBackgroundColor(getResources().getColor(android.R.color.holo_blue_light));
            modeStatusText.setTextColor(getResources().getColor(android.R.color.holo_blue_dark));
            modeSwitch.setText("Manual");

            // Enable sliders in manual mode
            gripper1.setEnabled(true);
            gripper2.setEnabled(true);
            gripper3.setEnabled(true);
            gripper1.setAlpha(1.0f);
            gripper2.setAlpha(1.0f);
            gripper3.setAlpha(1.0f);

            // Enable joystick in manual mode
            joystick.setEnabled(true);
            joystick.setAlpha(1.0f);
        } else {
            modeStatusText.setText("Mode: AUTONOMOUS");
            modeStatusText.setBackgroundColor(getResources().getColor(android.R.color.holo_green_light));
            modeStatusText.setTextColor(getResources().getColor(android.R.color.holo_green_dark));
            modeSwitch.setText("Autonomous");

            // Disable sliders in autonomous mode
            gripper1.setEnabled(false);
            gripper2.setEnabled(false);
            gripper3.setEnabled(false);
            gripper1.setAlpha(0.5f);
            gripper2.setAlpha(0.5f);
            gripper3.setAlpha(0.5f);

            // Disable joystick in autonomous mode (optional visual feedback)
            joystick.setEnabled(false);
            joystick.setAlpha(0.5f);
        }
    }

    private void sendModeCommand(String mode) {
        if (socket != null && isConnected) {
            String msg = "MODE:" + mode;
            socket.send(msg.getBytes(ZMQ.CHARSET));
            Log.d("ZMQ", "Sent mode command: " + msg);
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

        if (isConnected && isManualMode) sendCoordinate(valX, valY);
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

                    // Send initial mode command
                    if (isManualMode) {
                        sendModeCommand("MANUAL");
                    } else {
                        sendModeCommand("AUTO");
                    }
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
        // Only send if connected AND in manual mode
        if (socket != null && isConnected && isManualMode) {
            String msg = x + "," + y;
            socket.send(msg.getBytes(ZMQ.CHARSET));
            Log.d("ZMQ", "Sent: " + msg);
        }
    }

    private void disconnectFromServer() {
        new Thread(() -> {
            try {
                resetCoordinates();
                resetSliders();

                // Close joystick socket
                if (socket != null) {
                    socket.close();
                    socket = null;
                }
                if (context != null) {
                    context.close();
                    context = null;
                }

                isConnected = false;

                Log.d("ZMQ", "Disconnected from server");

                runOnUiThread(() -> {
                    btnConnect.setText("CONNECT");
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
        resetSliders();
        if (receiver != null) receiver.stopReceiver();
    }
}