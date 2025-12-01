package com.example.controllerzmq;

import java.util.Locale;
import android.content.Context;
import android.content.SharedPreferences;
import android.graphics.Bitmap;
import android.net.wifi.WifiInfo;
import android.net.wifi.WifiManager;
import android.os.Bundle;

import android.os.Handler;
import android.os.Looper;
import android.text.format.Formatter;
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

import java.net.InetAddress;
import java.net.NetworkInterface;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.atomic.AtomicReference;

public class MainActivity extends AppCompatActivity {

    private UDPReceiver receiver;
    private ImageView videoStream;
    private Button btnConnect, preset1, preset2, btnGripper, btnSendIP, btnReset;
    private ImageButton btnSetting, btnRotateRight, btnRotateLeft;
    private TextView koor, tvGripper1Value, tvGripper2Value, tvMyIP;
    private String msg;
    private JoystickView joystick;
    private TextView petunjuk;
    private SwitchMaterial modeSwitch;
    private SwitchMaterial modeSwitch2;  // NEW: KFS Team Switch
    private TextView modeStatusText;
    private Slider gripper1, gripper2;

    private float valX = 0f, valY = 0f, valRotation = 0f, valA = 0f, valB = 0f;

    private AtomicReference<Bitmap> latestFrame = new AtomicReference<>(null);
    private int frameReceived = 0;
    private int frameDropped = 0;

    private Handler handler = new Handler(Looper.getMainLooper());

    private ZContext context;
    private ZMQ.Socket socket;

    private boolean isConnected = false;
    private boolean isManualMode = true;
    private boolean isGripping = false;
    private boolean isReceiverRunning = false;
    private boolean preset1Active = false;
    private boolean preset2Active = false;
    private boolean isBlueTeam = true;  // NEW: Default Blue Team


    private String serverIp = "10.107.137.167";
    private int serverPort = 6000;
    private String myIpAddress = "";

    private SharedPreferences prefs;

    private final Runnable uiUpdateRunnable = new Runnable() {
        @Override
        public void run() {
            Bitmap frame = latestFrame.getAndSet(null);

            if (frame != null) {
                videoStream.setImageBitmap(frame);
                frameReceived++;

                if (frameReceived % 100 == 0) {
                    Log.d("UDP_FRAME", "Received: " + frameReceived + " | Dropped: " + frameDropped);
                }
            }

            if (isReceiverRunning) {
                handler.postDelayed(this, 33);
            }
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        EdgeToEdge.enable(this);
        setContentView(R.layout.activity_controller);

        videoStream = findViewById(R.id.videoStream);
        videoStream.setScaleType(ImageView.ScaleType.FIT_CENTER);

        receiver = new UDPReceiver(6000, bmp -> {
            Bitmap oldFrame = latestFrame.getAndSet(bmp);

            if (oldFrame != null) {
                frameDropped++;
                if (!oldFrame.isRecycled()) {
                    oldFrame.recycle();
                }
            }
        });

        receiver.start();
        isReceiverRunning = true;
        handler.post(uiUpdateRunnable);

        setupSystemInsets();

        prefs = getSharedPreferences("ZMQ_PREFS", MODE_PRIVATE);
        serverIp = prefs.getString("IP", serverIp);
        serverPort = prefs.getInt("PORT", serverPort);
        isBlueTeam = prefs.getBoolean("IS_BLUE_TEAM", true);  // NEW: Load saved team

        // Get IP address
        myIpAddress = getIPAddress();

        // init views
        btnConnect = findViewById(R.id.btnConnect);
        btnSetting = findViewById(R.id.btnSetting);
        koor = findViewById(R.id.koord);
        joystick = findViewById(R.id.joystick);
        petunjuk = findViewById(R.id.valJoy);
        btnRotateRight = findViewById(R.id.btnRotateRight);
        btnRotateLeft = findViewById(R.id.btnRotateLeft);
        modeSwitch = findViewById(R.id.modeSwitch);
        modeSwitch2 = findViewById(R.id.teamSwitch);  // NEW: Init KFS Team Switch
        modeStatusText = findViewById(R.id.modeStatusText);

        gripper1 = findViewById(R.id.gripper);
        gripper2 = findViewById(R.id.gripper2);

        tvGripper1Value = findViewById(R.id.tvGripper1Value);
        tvGripper2Value = findViewById(R.id.tvGripper2Value);

        preset1 = findViewById(R.id.preset1);
        preset2 = findViewById(R.id.preset2);
        btnGripper = findViewById(R.id.btnGripper);
        btnReset = findViewById(R.id.reset);  // NEW: Init reset button

        // Display my IP
//        tvMyIP.setText("My IP: " + myIpAddress);

        setupSliderListeners();
        setupPresetButtons();
        setupGripperButton();
        setupResetButton();  // NEW: Setup reset button
//        setupSendIPButton();

        // NEW: Setup KFS Team Switch
        modeSwitch2.setChecked(isBlueTeam);
        modeSwitch2.setOnCheckedChangeListener((buttonView, isChecked) -> {
            isBlueTeam = isChecked;
            updateTeamDisplay();

            // Save preference
            prefs.edit().putBoolean("IS_BLUE_TEAM", isBlueTeam).apply();

            if (isConnected) {
                if (isBlueTeam) {
                    sendTeamCommand("KFS-Blue");
                    Toast.makeText(this, "Team: Blue", Toast.LENGTH_SHORT).show();
                } else {
                    sendTeamCommand("KFS-Red");
                    Toast.makeText(this, "Team: Red", Toast.LENGTH_SHORT).show();
                }
            }
        });
        updateTeamDisplay();  // Set tampilan awal

        modeSwitch.setOnCheckedChangeListener((buttonView, isChecked) -> {
            isManualMode = isChecked;
            updateModeDisplay();

            if (isConnected) {
                if (isManualMode) {
                    sendModeCommand("MANUAL");
                    Toast.makeText(this, "Switched to Manual Mode", Toast.LENGTH_SHORT).show();
                } else {
                    sendModeCommand("AUTO");
                    Toast.makeText(this, "Switched to Autonomous Mode", Toast.LENGTH_SHORT).show();
                }
            }
        });

        btnConnect.setOnClickListener(v -> {
            if (!isConnected) connectToServer();
            else disconnectFromServer();
        });

        btnSetting.setOnClickListener(v -> showIpPortDialog());

        // ROTATE LEFT BUTTON
        btnRotateLeft.setOnTouchListener((v, event) -> {
            switch (event.getAction()) {
                case android.view.MotionEvent.ACTION_DOWN:
                    sendRotateValue(-5);   // tekan = -5
                    return true;

                case android.view.MotionEvent.ACTION_UP:
                case android.view.MotionEvent.ACTION_CANCEL:
                    sendRotateValue(0);    // lepas = kembali ke 0
                    return true;
            }
            return false;
        });

        // ROTATE RIGHT BUTTON
        btnRotateRight.setOnTouchListener((v, event) -> {
            switch (event.getAction()) {
                case android.view.MotionEvent.ACTION_DOWN:
                    sendRotateValue(+5);  // tekan = +5
                    return true;

                case android.view.MotionEvent.ACTION_UP:
                case android.view.MotionEvent.ACTION_CANCEL:
                    sendRotateValue(0);   // lepas = 0
                    return true;
            }
            return false;
        });

        joystick.setJoystickListener(new JoystickView.JoystickListener() {
            @Override
            public void onJoystickMoved(float xPercent, float yPercent, int direction) {
                valX = xPercent;
                valY = yPercent;

                updateCoordinateDisplay();

                if (isConnected && isManualMode) {
                    sendCoordinate(valX, valY);
                }

                String dirText = getDirectionText(direction);
                petunjuk.setText(String.format("X: %.2f | Y: %.2f\n%s",
                        xPercent, yPercent, dirText));
            }
        });

        updateModeDisplay();
    }

    // Method to get IP Address
    private String getIPAddress() {
        try {
            // Try WiFi first
            WifiManager wifiManager = (WifiManager) getApplicationContext().getSystemService(Context.WIFI_SERVICE);
            if (wifiManager != null) {
                WifiInfo wifiInfo = wifiManager.getConnectionInfo();
                int ipInt = wifiInfo.getIpAddress();
                if (ipInt != 0) {
                    return Formatter.formatIpAddress(ipInt);
                }
            }

            // Fallback: get from network interfaces
            List<NetworkInterface> interfaces = Collections.list(NetworkInterface.getNetworkInterfaces());
            for (NetworkInterface intf : interfaces) {
                List<InetAddress> addrs = Collections.list(intf.getInetAddresses());
                for (InetAddress addr : addrs) {
                    if (!addr.isLoopbackAddress()) {
                        String sAddr = addr.getHostAddress();
                        boolean isIPv4 = sAddr.indexOf(':') < 0;
                        if (isIPv4) {
                            return sAddr;
                        }
                    }
                }
            }
        } catch (Exception e) {
            Log.e("IP_ADDRESS", "Failed to get IP address", e);
        }
        return "Unknown";
    }

    private void sendIPAddress() {
        if (socket != null && isConnected) {
            String msg = "CLIENT_IP:" + myIpAddress;
            socket.send(msg.getBytes(ZMQ.CHARSET));
            Log.d("ZMQ", "Sent IP address: " + msg);
            Toast.makeText(this, "IP Address sent: " + myIpAddress, Toast.LENGTH_SHORT).show();
        }
    }

    // NEW: Setup Reset Button
    private void setupResetButton() {
        btnReset.setOnClickListener(v -> {
            if (!isConnected) {
                Toast.makeText(this, "Not connected to server", Toast.LENGTH_SHORT).show();
                return;
            }

            resetAllValues();
            Toast.makeText(this, "All values reset to 0", Toast.LENGTH_SHORT).show();
        });
    }

    // NEW: Reset All Values to 0
    private void resetAllValues() {
        // Reset koordinat joystick
        valX = 0f;
        valY = 0f;
        updateCoordinateDisplay();
        if (isConnected) {
            sendCoordinate(0f, 0f);
        }

        // Reset rotasi
        valRotation = 0f;
        if (isConnected) {
            sendRotateValue(0);
        }

        // Reset sliders
        valA = 0f;
        valB = 0f;
        gripper1.setValue(0f);
        gripper2.setValue(0f);
        tvGripper1Value.setText("Motor 1: 0.00");
        tvGripper2Value.setText("Motor 2: 0.00");
        if (isConnected) {
            sendSliderData();
        }

        // Reset gripper
        if (isGripping) {
            isGripping = false;
            btnGripper.setText("GRIPPER");
            btnGripper.setBackgroundColor(getResources().getColor(android.R.color.darker_gray));
            if (isConnected) {
                sendGripperCommand(0);
            }
        }

        // Reset presets
        if (preset1Active || preset2Active) {
            preset1Active = false;
            preset2Active = false;
            if (isConnected) {
                sendPresetCommand(0);
            }
        }

//        // Reset joystick visual (jika ada method reset di JoystickView)
//        if (joystick != null) {
//            joystick.reset();
//        }

        // Update display
        petunjuk.setText("X: 0.00 | Y: 0.00\nCENTER ●");

        Log.d("ZMQ", "All values reset to 0");
    }

    private void setupGripperButton() {
        btnGripper.setOnClickListener(v -> toggleGripper());
    }

    private void toggleGripper() {
        if (!isConnected) {
            Toast.makeText(this, "Not connected to server", Toast.LENGTH_SHORT).show();
            return;
        }

        if (!isManualMode) {
            Toast.makeText(this, "Gripper only works in Manual Mode", Toast.LENGTH_SHORT).show();
            return;
        }

        isGripping = !isGripping;

        if (isGripping) {
            // ON
            btnGripper.setText("GRIPPING");
            btnGripper.setBackgroundColor(getResources().getColor(android.R.color.holo_green_light));
            sendGripperCommand(1);
            Toast.makeText(this, "Gripper Activated", Toast.LENGTH_SHORT).show();
        } else {
            // OFF
            btnGripper.setText("GRIPPER");
            btnGripper.setBackgroundColor(getResources().getColor(android.R.color.darker_gray));
            sendGripperCommand(0);
            Toast.makeText(this, "Gripper Released", Toast.LENGTH_SHORT).show();
        }
    }

    private void sendGripperCommand(int value) {
        if (socket != null && isConnected && isManualMode) {
            String msg = "GRIPPER:" + value;
            socket.send(msg.getBytes(ZMQ.CHARSET));
            Log.d("ZMQ", "Sent gripper command: " + msg);
        }
    }


    private void setupPresetButtons() {
        preset1.setOnClickListener(v -> {
            if (!isConnected) {
                Toast.makeText(this, "Not connected to server", Toast.LENGTH_SHORT).show();
                return;
            }

            if (!preset1Active) {
                sendPresetCommand(1);   // ON
                preset1Active = true;
                Toast.makeText(this, "Preset 1 activated", Toast.LENGTH_SHORT).show();
            } else {
                sendPresetCommand(0);   // OFF
                preset1Active = false;
                Toast.makeText(this, "Preset 1 deactivated", Toast.LENGTH_SHORT).show();
            }
        });

        preset2.setOnClickListener(v -> {
            if (!isConnected) {
                Toast.makeText(this, "Not connected to server", Toast.LENGTH_SHORT).show();
                return;
            }

            if (!preset2Active) {
                sendPresetCommand(2);
                preset2Active = true;
                Toast.makeText(this, "Preset 2 activated", Toast.LENGTH_SHORT).show();
            } else {
                sendPresetCommand(0);
                preset2Active = false;
                Toast.makeText(this, "Preset 2 deactivated", Toast.LENGTH_SHORT).show();
            }
        });
    }

    private void sendPresetCommand(int presetNumber) {
        if (socket != null && isConnected) {
            String msg = "PRESET:" + presetNumber;
            socket.send(msg.getBytes(ZMQ.CHARSET));
            Log.d("ZMQ", "Sent preset command: " + msg);
        }
    }

    private void setupSliderListeners() {
        gripper1.addOnChangeListener((slider, value, fromUser) -> {
            valA = value;
            tvGripper1Value.setText(String.format("Motor 1: %.2f", valA));

            if (isConnected && isManualMode) {
                sendSliderData();
            }
        });

        gripper2.addOnChangeListener((slider, value, fromUser) -> {
            valB = value;
            tvGripper2Value.setText(String.format("Motor 2: %.2f", valB));

            if (isConnected && isManualMode) {
                sendSliderData();
            }
        });
    }

    private void sendSliderData() {
        if (socket != null && isConnected && isManualMode) {
            String msg = String.format(Locale.US,"SLIDER:%.2f,%.2f", valA, valB);
            socket.send(msg.getBytes(ZMQ.CHARSET));
            Log.d("ZMQ", "Sent slider data: " + msg);
        }
    }

    private void resetSliders() {
        valA = 0f;
        valB = 0f;

        gripper1.setValue(0f);
        gripper2.setValue(0f);

        tvGripper1Value.setText("Motor 1: 0.00");
        tvGripper2Value.setText("Motor 2: 0.00");

        isGripping = false;
        if (btnGripper != null) {
            btnGripper.setText("GRIPPER");
            btnGripper.setBackgroundColor(getResources().getColor(android.R.color.darker_gray));
        }

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

            gripper1.setEnabled(true);
            gripper2.setEnabled(true);
            gripper1.setAlpha(1.0f);
            gripper2.setAlpha(1.0f);

            joystick.setEnabled(true);
            joystick.setAlpha(1.0f);

            btnGripper.setEnabled(true);
            btnGripper.setAlpha(1.0f);

        } else {
            modeStatusText.setText("Mode: AUTONOMOUS");
            modeStatusText.setBackgroundColor(getResources().getColor(android.R.color.holo_green_light));
            modeStatusText.setTextColor(getResources().getColor(android.R.color.holo_green_dark));
            modeSwitch.setText("Autonomous");

            gripper1.setEnabled(false);
            gripper2.setEnabled(false);
            gripper1.setAlpha(0.5f);
            gripper2.setAlpha(0.5f);

            joystick.setEnabled(false);
            joystick.setAlpha(0.5f);

            btnGripper.setEnabled(false);
            btnGripper.setAlpha(0.5f);

            if (isGripping) {
                isGripping = false;
                btnGripper.setText("GRIPPER");
                btnGripper.setBackgroundColor(getResources().getColor(android.R.color.darker_gray));
            }
        }
    }

    // NEW: Update tampilan KFS Team Switch
    private void updateTeamDisplay() {
        if (isBlueTeam) {
            // Blue Team - Switch ON
            modeSwitch2.setText("Blue");
            modeSwitch2.setTextColor(getResources().getColor(android.R.color.holo_blue_dark));
        } else {
            // Red Team - Switch OFF
            modeSwitch2.setText("Red");
            modeSwitch2.setTextColor(getResources().getColor(android.R.color.holo_red_dark));
        }
    }

    // NEW: Kirim perintah team ke server
    private void sendTeamCommand(String team) {
        if (socket != null && isConnected) {
            socket.send(team.getBytes(ZMQ.CHARSET));
            Log.d("ZMQ", "Sent team command: " + team);
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
            case 2: return "KANAN BAWAH ↘";
            case 3: return "KANAN →";
            case 4: return "KANAN ATAS ↗";
            case 5: return "BAWAH ↓";
            case 6: return "KIRI ATAS ↖";
            case 7: return "KIRI ←";
            case 8: return "KIRI BAWAH ↙";
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

                    if (isManualMode) {
                        sendModeCommand("MANUAL");
                    } else {
                        sendModeCommand("AUTO");
                    }
                    sendIPAddress();

                    // NEW: Kirim team command saat connect
                    if (isBlueTeam) {
                        sendTeamCommand("KFS-Blue");
                    } else {
                        sendTeamCommand("KFS-Red");
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
        if (socket != null && isConnected && isManualMode) {
            String msg = String.format(Locale.US, "%.2f,%.2f", x, y);
            socket.send(msg.getBytes(ZMQ.CHARSET));
            Log.d("ZMQ", "Sent: " + msg);
        }
    }

    private void sendRotateValue(int value) {
        if (socket != null && isConnected && isManualMode) {
            String msg = "ROTATE:" + value;
            socket.send(msg.getBytes(ZMQ.CHARSET));
            Log.d("ZMQ", "Sent rotate: " + msg);
        }
    }

    private void disconnectFromServer() {
        new Thread(() -> {
            try {
                resetCoordinates();
                resetSliders();

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

        isReceiverRunning = false;
        handler.removeCallbacks(uiUpdateRunnable);

        disconnectFromServer();
        resetCoordinates();
        resetSliders();

        if (receiver != null) {
            receiver.stopReceiver();
        }

        Bitmap lastFrame = latestFrame.getAndSet(null);
        if (lastFrame != null && !lastFrame.isRecycled()) {
            lastFrame.recycle();
        }

        videoStream.setImageBitmap(null);

        Log.d("UDP_FRAME", "Final stats - Received: " + frameReceived + " | Dropped: " + frameDropped);
    }
}