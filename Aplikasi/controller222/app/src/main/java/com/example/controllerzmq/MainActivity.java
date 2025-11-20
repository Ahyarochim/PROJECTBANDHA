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
//    private Button button;
    private Button btnConnect, btnAuto;
    private ImageButton btnSetting, btnRotateRight, btnRotateLeft;
    private TextView koor;
    private String msg;
    private JoystickView joystick;
    private TextView petunjuk;

    private float valX = 0f, valY = 0f, valRotation =0f;

    private Handler handler = new Handler(Looper.getMainLooper());

    private ZContext context;
    private ZMQ.Socket socket;
    private boolean isConnected = false;
//    private int kondisiLed = 1;

    private String serverIp ="10.107.137.167";
    private int serverPort = 6000;

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
        btnAuto = findViewById(R.id.btnAuto);



        // connect/disconnect button
        btnConnect.setOnClickListener(v -> {
            if (!isConnected) connectToServer();
            else disconnectFromServer();
        });

        // settings button
        btnSetting.setOnClickListener(v -> showIpPortDialog());

        //automatic connect
        handler.postDelayed(() -> {
            if (!isConnected) connectToServer();
        }, 500);


        // Setup joystick listener
        joystick.setJoystickListener(new JoystickView.JoystickListener() {
            @Override
            public void onJoystickMoved(float xPercent, float yPercent, int direction) {
                // Convert percentage to your coordinate system (0-180)
                valX = xPercent  * 90; // converts -1 to 1 into 0 to 180
                valY = -yPercent  * 90; // converts -1 to 1 into 0 to 180

                updateCoordinateDisplay();

                if (isConnected) {
                    sendCoordinate(valX, valY);
                }

                // Update petunjuk text
                String dirText = getDirectionText(direction);
                petunjuk.setText(String.format("X: %.2f | Y: %.2f\n%s",
                        xPercent, yPercent, dirText));
            }
        });
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

        // Kirim reset ke server jika masih terhubung
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

                    // Save for next auto-connect
                    prefs.edit().putString("IP", serverIp).putInt("PORT", serverPort).apply();

                    disconnectFromServer(); // disconnect if already connected
                    connectToServer();      // connect to new server
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
                runOnUiThread(() -> {
                    btnConnect.setText("DISCONNECT");
                    Toast.makeText(this, "Connected to server", Toast.LENGTH_SHORT).show();
                });
            } catch (Exception e) {
                Log.e("ZMQ", "Connection failed", e);
                runOnUiThread(() -> Toast.makeText(this, "Connection failed", Toast.LENGTH_SHORT).show());
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

    //Testing
//    private void nyalakanLed() {
//        if (socket != null && isConnected) {
//            if (kondisiLed == 0) {
//                msg = "0";
//                kondisiLed = 1;
//            } else if (kondisiLed == 1) {
//                msg = "1";
//                kondisiLed = 0;
//            }
//            socket.send(msg.getBytes(ZMQ.CHARSET));
//            Log.d("ZMQ", "Sent: " + msg);
//            runOnUiThread(() -> {
//                Toast.makeText(this, "Data terkirim", Toast.LENGTH_SHORT).show();
//            });
//        }
//    }

    private void disconnectFromServer() {
        new Thread(() -> {
            try {
                resetCoordinates();
                if (socket != null) socket.close();
                if (context != null) context.close();
                isConnected = false;
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
        if (receiver != null) receiver.stopReceiver();

    }
}