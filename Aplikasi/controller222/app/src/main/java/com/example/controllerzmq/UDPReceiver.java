package com.example.controllerzmq;

import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.util.Log;

import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.SocketTimeoutException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class UDPReceiver {
    public interface FrameListener {
        void onFrameReceived(Bitmap bitmap);
    }

    private int port;
    private FrameListener listener;
    private boolean running = false;
    private Thread receiveThread;
    private ExecutorService decodeExecutor; // Thread pool untuk decode

    private static final int MAX_PACKET_SIZE = 65536;
    private static final String TAG = "UDPReceiver";

    // Frame skipping untuk menghindari backlog
    private volatile boolean isDecoding = false;

    // Reusable BitmapFactory options untuk efisiensi
    private final BitmapFactory.Options bitmapOptions = new BitmapFactory.Options();

    public UDPReceiver(int port, FrameListener listener) {
        this.port = port;
        this.listener = listener;

        // Setup bitmap options untuk decode lebih cepat
        bitmapOptions.inPreferredConfig = Bitmap.Config.RGB_565; // 16-bit (lebih ringan dari ARGB_8888)
        bitmapOptions.inMutable = true; // Reusable
        bitmapOptions.inTempStorage = new byte[16 * 1024]; // 16KB buffer

        // Single thread executor untuk decode (avoid thread overhead)
        decodeExecutor = Executors.newSingleThreadExecutor();
    }

    public void start() {
        running = true;
        receiveThread = new Thread(() -> {
            try {
                DatagramSocket socket = new DatagramSocket(port);
                socket.setReceiveBufferSize(131072); // 128KB buffer (lebih besar)
                socket.setSoTimeout(2000);

                Log.d(TAG, "✓ Socket started on port " + port);

                byte[] buffer = new byte[MAX_PACKET_SIZE];

                while (running) {
                    try {
                        // Receive packet
                        DatagramPacket packet = new DatagramPacket(buffer, buffer.length);
                        socket.receive(packet);

                        int packetLength = packet.getLength();

                        if (packetLength < 8) {
                            continue;
                        }

                        // Parse header
                        String sizeStr = new String(buffer, 0, 8, "ASCII");
                        int imageSize;

                        try {
                            imageSize = Integer.parseInt(sizeStr.trim());
                        } catch (NumberFormatException e) {
                            continue;
                        }

                        if (imageSize <= 0 || imageSize > MAX_PACKET_SIZE - 8) {
                            continue;
                        }

                        // ===== FRAME SKIPPING: Skip kalau masih decode frame sebelumnya =====
                        if (isDecoding) {
                            Log.d(TAG, "⏭ Skipping frame (still decoding previous)");
                            continue;
                        }

                        // Copy image data (harus copy karena buffer di-reuse)
                        byte[] imageData = new byte[imageSize];
                        System.arraycopy(buffer, 8, imageData, 0, imageSize);

                        // Check JPEG signature
                        if (imageData[0] != (byte)0xFF || imageData[1] != (byte)0xD8) {
                            continue;
                        }

                        // ===== DECODE DI BACKGROUND THREAD =====
                        isDecoding = true;
                        decodeExecutor.execute(() -> {
                            try {
                                // Decode bitmap dengan options yang sudah di-optimize
                                Bitmap bmp = BitmapFactory.decodeByteArray(
                                        imageData, 0, imageSize, bitmapOptions
                                );

                                if (bmp != null && listener != null) {
                                    listener.onFrameReceived(bmp);
                                }
                            } catch (Exception e) {
                                Log.e(TAG, "Decode error", e);
                            } finally {
                                isDecoding = false;
                            }
                        });

                    } catch (SocketTimeoutException e) {
                        // Normal timeout
                    }
                }

                socket.close();
                Log.d(TAG, "Socket closed");

            } catch (Exception e) {
                Log.e(TAG, "FATAL ERROR", e);
            }
        });
        receiveThread.start();
    }

    public void stopReceiver() {
        running = false;

        if (decodeExecutor != null) {
            decodeExecutor.shutdownNow();
        }

        if (receiveThread != null) {
            receiveThread.interrupt();
        }
    }
}