import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { OVERLOAD_ALERTS_QUERY_KEY } from "../services/analytics_api";

const OVERLOAD_RESOLVED_EVENT = "overload.resolved";

function getWebSocketUrl() {
  if (import.meta.env.VITE_WS_URL) {
    return import.meta.env.VITE_WS_URL;
  }

  const url = new URL("/api/v1/ws", window.location.origin);
  url.protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return url.toString();
}

export default function useRealtime() {
  const queryClient = useQueryClient();

  useEffect(() => {
    let socket = null;
    let reconnectTimerId = null;
    let heartbeatTimerId = null;
    let reconnectAttempt = 0;
    let stopped = false;

    const stopHeartbeat = () => {
      if (heartbeatTimerId !== null) {
        window.clearInterval(heartbeatTimerId);
        heartbeatTimerId = null;
      }
    };

    const scheduleReconnect = () => {
      if (stopped || reconnectTimerId !== null) {
        return;
      }

      const backoff = Math.min(1_000 * 2 ** reconnectAttempt, 30_000);
      const jitter = Math.floor(Math.random() * 500);
      reconnectAttempt += 1;

      reconnectTimerId = window.setTimeout(() => {
        reconnectTimerId = null;
        connect();
      }, backoff + jitter);
    };

    const connect = () => {
      if (stopped) {
        return;
      }

      const currentSocket = new WebSocket(getWebSocketUrl());
      socket = currentSocket;

      currentSocket.onopen = () => {
        reconnectAttempt = 0;
        heartbeatTimerId = window.setInterval(() => {
          if (currentSocket.readyState === WebSocket.OPEN) {
            currentSocket.send("ping");
          }
        }, 25_000);
      };

      currentSocket.onmessage = (event) => {
        let message;
        try {
          message = JSON.parse(event.data);
        } catch {
          return;
        }

        if (message?.type !== OVERLOAD_RESOLVED_EVENT) {
          return;
        }

        void queryClient.invalidateQueries(
          {
            queryKey: OVERLOAD_ALERTS_QUERY_KEY,
            exact: true,
          },
          {
            cancelRefetch: false,
          },
        );
      };

      currentSocket.onerror = () => {
        currentSocket.close();
      };

      currentSocket.onclose = () => {
        stopHeartbeat();
        if (socket === currentSocket) {
          socket = null;
        }
        scheduleReconnect();
      };
    };

    connect();

    return () => {
      stopped = true;
      stopHeartbeat();

      if (reconnectTimerId !== null) {
        window.clearTimeout(reconnectTimerId);
      }

      if (socket) {
        socket.close(1000, "layout unmounted");
      }
    };
  }, [queryClient]);
}
