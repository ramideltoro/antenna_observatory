'use client';

import { useEffect, useRef, useState } from 'react';
import { BellRing, Download, Gauge, Radio, Smartphone } from 'lucide-react';
import type { HealthScore, SmartAlert } from '@/lib/telemetry';
import { Button } from '@/components/ui/button';

interface InstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
}
const EMPTY_ALERTS: SmartAlert[] = [];

export function HealthSummary({ health }: { health?: HealthScore }) {
  const score = health?.score ?? 0;
  return (
    <section
      className="health-score-summary"
      aria-label="Automatic antenna health score"
    >
      <div
        className="health-gauge"
        style={{ '--score': score } as React.CSSProperties}
      >
        <span>
          <strong>{health ? score : '—'}</strong>
          <small>/100</small>
        </span>
      </div>
      <div className="health-copy">
        <span>
          <Gauge size={16} /> Automatic antenna health
        </span>
        <h2>{health?.status || 'Calculating station health'}</h2>
        <p>
          {health?.reasons[0] ||
            'Waiting for current receiver and feed measurements.'}
        </p>
      </div>
      <div className="health-components">
        {Object.entries(health?.components || {}).map(([name, value]) => (
          <div key={name}>
            <span>{name}</span>
            <i>
              <b
                style={{
                  width: `${(value / (name === 'availability' ? 40 : name === 'radio' ? 25 : name === 'quality' ? 20 : 15)) * 100}%`,
                }}
              />
            </i>
            <strong>{value}</strong>
          </div>
        ))}
      </div>
    </section>
  );
}

export function PwaControls({
  visible,
  alerts = EMPTY_ALERTS,
}: {
  visible: boolean;
  alerts?: SmartAlert[];
}) {
  const [prompt, setPrompt] = useState<InstallPromptEvent | null>(null);
  const [installed, setInstalled] = useState(
    () =>
      typeof window !== 'undefined' &&
      window.matchMedia('(display-mode: standalone)').matches,
  );
  const [notification, setNotification] = useState(() =>
    typeof Notification === 'undefined'
      ? 'unsupported'
      : Notification.permission,
  );
  const previousAlerts = useRef<Set<string>>(new Set());
  useEffect(() => {
    const ready = (event: Event) => {
      event.preventDefault();
      setPrompt(event as InstallPromptEvent);
    };
    const complete = () => {
      setInstalled(true);
      setPrompt(null);
    };
    window.addEventListener('beforeinstallprompt', ready);
    window.addEventListener('appinstalled', complete);
    const syncNotification = () =>
      setNotification(
        typeof Notification === 'undefined'
          ? 'unsupported'
          : Notification.permission,
      );
    window.addEventListener(
      'antenna-notification-permission',
      syncNotification,
    );
    if ('serviceWorker' in navigator)
      void navigator.serviceWorker.register('/sw.js');
    return () => {
      window.removeEventListener('beforeinstallprompt', ready);
      window.removeEventListener('appinstalled', complete);
      window.removeEventListener(
        'antenna-notification-permission',
        syncNotification,
      );
    };
  }, []);
  useEffect(() => {
    if (notification !== 'granted') return;
    alerts.forEach((alert) => {
      if (!previousAlerts.current.has(alert.code))
        new Notification(`Antenna Observatory · ${alert.title}`, {
          body: alert.message,
          icon: '/icons/icon-192.png',
          tag: alert.code,
        });
    });
    previousAlerts.current = new Set(alerts.map((alert) => alert.code));
  }, [alerts, notification]);
  const install = async () => {
    if (!prompt) return;
    await prompt.prompt();
    const choice = await prompt.userChoice;
    if (choice.outcome === 'accepted') setPrompt(null);
  };
  const notify = async () => {
    if (typeof Notification !== 'undefined') {
      setNotification(await Notification.requestPermission());
      window.dispatchEvent(new Event('antenna-notification-permission'));
    }
  };
  if (!visible) return null;
  return (
    <section className="panel pwa-panel">
      <div className="panel-heading">
        <div>
          <h2>Mobile app & notifications</h2>
          <p>
            Install the dashboard and receive live condition alerts while it is
            open.
          </p>
        </div>
        <Smartphone size={20} />
      </div>
      <div className="pwa-options">
        <article>
          <span>
            <Download size={20} />
          </span>
          <div>
            <strong>
              {installed ? 'Observatory installed' : 'Install on this device'}
            </strong>
            <p>
              Launches full-screen with the amber app icon and the same live
              public receiver views.
            </p>
          </div>
          <Button
            onClick={() => void install()}
            disabled={installed || !prompt}
          >
            {installed ? 'Installed' : prompt ? 'Install' : 'Use browser menu'}
          </Button>
        </article>
        <article>
          <span>
            <BellRing size={20} />
          </span>
          <div>
            <strong>Smart alert notifications</strong>
            <p>
              Shows new receiver, noise, traffic, sample-loss, feed, and
              emergency conditions.
            </p>
          </div>
          <Button
            variant="outline"
            onClick={() => void notify()}
            disabled={
              notification === 'granted' || notification === 'unsupported'
            }
          >
            {notification === 'granted'
              ? 'Enabled'
              : notification === 'unsupported'
                ? 'Unavailable'
                : 'Enable'}
          </Button>
        </article>
        <article className="pwa-privacy">
          <span>
            <Radio size={20} />
          </span>
          <div>
            <strong>Private by design</strong>
            <p>
              The service worker does not cache telemetry, credentials, API
              responses, or protected pages.
            </p>
          </div>
        </article>
      </div>
    </section>
  );
}
