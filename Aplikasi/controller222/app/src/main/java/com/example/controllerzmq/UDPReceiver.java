package com.example.controllerzmq;

import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.util.Log;

import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.SocketTimeoutException;

public class UDPReceiver {

    public interface FrameListener {
        void onFrameReceived(Bitmap bitmap);
    }

    private int port;
    private FrameListener listener;
    private boolean running = false;
    private Thread thread;

    private static final int MAX_PACKET_SIZE = 65536; // 64 KB
    private static final String TAG = "UDPReceiver";

    public UDPReceiver(int port, FrameListener listener) {
        this.port = port;
        this.listener = listener;
    }

    public void start() {
        running = true;

        thread = new Thread(() -> {
            try {
                DatagramSocket socket = new DatagramSocket(port);
                socket.setReceiveBufferSize(65536);
                socket.setSoTimeout(2000);

                Log.d(TAG, "✓ Socket started on port " + port);

                byte[] buffer = new byte[MAX_PACKET_SIZE];

                while (running) {
                    try {
                        // --- RECEIVE SATU PAKET (Header + Data) ---
                        DatagramPacket packet = new DatagramPacket(buffer, buffer.length);
                        socket.receive(packet);

                        int packetLength = packet.getLength();
                        Log.d(TAG, "Received packet: " + packetLength + " bytes");

                        if (packetLength < 8) {
                            Log.e(TAG, "⚠ Packet too small: " + packetLength);
                            continue;
                        }

                        // Parse header 8 bytes (ASCII string)
                        String sizeStr = new String(buffer, 0, 8, "ASCII");
                        Log.d(TAG, "Header: [" + sizeStr + "]");

                        int imageSize;
                        try {
                            imageSize = Integer.parseInt(sizeStr.trim());
                        } catch (NumberFormatException e) {
                            Log.e(TAG, "⚠ Invalid header: " + sizeStr);
                            continue;
                        }

                        Log.d(TAG, "Image size: " + imageSize);

                        if (imageSize <= 0 || imageSize > MAX_PACKET_SIZE - 8) {
                            Log.e(TAG, "⚠ Invalid size: " + imageSize);
                            continue;
                        }

                        // Extract JPEG data (skip first 8 bytes)
                        byte[] imageData = new byte[imageSize];
                        System.arraycopy(buffer, 8, imageData, 0, imageSize);

                        // Check JPEG signature
                        if (imageData[0] != (byte)0xFF || imageData[1] != (byte)0xD8) {
                            Log.e(TAG, "⚠ Not a valid JPEG");
                            continue;
                        }

                        // Decode bitmap
                        Bitmap bmp = BitmapFactory.decodeByteArray(imageData, 0, imageSize);

                        if (bmp != null && listener != null) {
                            listener.onFrameReceived(bmp);
                            Log.d(TAG, "✓ Frame decoded: " + bmp.getWidth() + "x" + bmp.getHeight());
                        } else {
                            Log.e(TAG, "⚠ Bitmap decode failed");
                        }

                    } catch (SocketTimeoutException e) {
                        // Normal timeout, continue waiting
                    }
                }

                socket.close();
                Log.d(TAG, "Socket closed");

            } catch (Exception e) {
                Log.e(TAG, "FATAL ERROR", e);
            }
        });

        thread.start();
    }

    public void stopReceiver() {
        running = false;
        if (thread != null) {
            thread.interrupt();
        }
    }
}