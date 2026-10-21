/* אזור: העלאת טפסים — שלבי העבודה, גרירה, והתקדמות חיה (גלגל אחוזים + אריחים). */
import { useRef, useState } from 'react';
import { S } from '../store';
import { upload } from '../actions';
import { Btn } from './Bits';

const STEPS = [['1', 'העלאה'], ['2', 'בדיקה ואישור'], ['3', 'ייצוא לאקסל']];

export function UploadStrip() {
  const file = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const drag = (on: boolean) => (e: React.DragEvent) => { e.preventDefault(); setOver(on); };
  return (
    <section className={'strip' + (S.page === 'records' ? ' hidden' : '')} id="uploadStrip" aria-labelledby="uploadTitle">
      <h2 className="sr-only" id="uploadTitle">העלאת טפסים</h2>

      {/* שלבי העבודה: פס דק אחד, בלי כרטיסים */}
      <ol className="steps" id="steps" aria-label="שלבי העבודה">
        {STEPS.map(([n, label]) => {
          const step = Number(n);
          const cls = step === S.step ? 'now' : step < S.step ? 'done' : '';
          return <li key={n} data-step={n} className={cls || undefined} aria-current={step === S.step ? 'step' : undefined}>
            <b>{n}</b><span>{label}</span></li>;
        })}
      </ol>

      <section id="drop" className={'card' + (over ? ' over' : '') + (S.dropVisible ? '' : ' hidden')} aria-label="העלאת טפסים"
        onClick={() => file.current?.click()}
        onDragEnter={drag(true)} onDragOver={drag(true)} onDragLeave={drag(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); upload(e.dataTransfer.files); }}>
        <svg className="hero" viewBox="0 0 320 120" aria-hidden="true">
          <g className="sheets">
            <rect x="18" y="22" width="62" height="80" rx="6" className="sheet s3" />
            <rect x="30" y="14" width="62" height="80" rx="6" className="sheet s2" />
            <rect x="42" y="6" width="62" height="80" rx="6" className="sheet s1" />
            <path d="M54 26h38M54 38h30M54 50h38M54 62h22" className="ink" />
            <path d="M60 74h30" className="ink hand" />
          </g>
          <path d="M128 56h56" className="arrow" />
          <path d="M176 46l12 10-12 10" className="arrow" />
          <g className="grid">
            <rect x="206" y="18" width="98" height="78" rx="7" className="tablebox" />
            <path d="M206 38h98M206 58h98M206 78h98M240 18v78M272 18v78" className="gridline" />
            <rect x="241" y="39" width="30" height="18" className="hl" />
            <rect x="273" y="59" width="30" height="18" className="ok" />
          </g>
        </svg>
        <h3>גררו לכאן טפסים</h3>
        <p>או</p>
        <div className="actions">
          <Btn className="primary big" id="browse" onClick={(e) => { e.stopPropagation(); file.current?.click(); }}>בחירת קבצים</Btn>
        </div>
        <input type="file" id="file" ref={file} className="hidden" accept=".pdf,.jpg,.jpeg,.png" multiple
          onClick={(e) => e.stopPropagation()} onChange={(e) => upload(e.target.files)} />
        <small id="limits">{S.config ? 'PDF, JPG או PNG · עד ' + S.config.max_pages + ' טפסים בכל פעם' : 'PDF, JPG או PNG'}</small>
      </section>

      {/* התקדמות חיה: גלגל שסופר את הטפסים, ומאחוריו הטפסים עולים כאריחים בהירים */}
      <section id="progress" className={'card' + (S.progressVisible ? '' : ' hidden')} aria-label="התקדמות הקריאה">
        <div className="stage">
          <div className="tiles" id="tiles" aria-hidden="true">
            {S.tiles.map((t: any) => <ProgressTile key={t.id} tile={t} />)}
          </div>
          <div className="veil" aria-hidden="true"></div>
          <div className="ringbox" id="ringbox" role="status" aria-live="polite">
            <div className="ringinner">
              <div className={S.ring.cls} id="ring">
                <svg viewBox="0 0 120 120" aria-hidden="true">
                  <defs>
                    <linearGradient id="ringGrad" x1="0" y1="0" x2="1" y2="1">
                      <stop offset="0" stopColor="#0068f5" /><stop offset="1" stopColor="#00a8cc" />
                    </linearGradient>
                  </defs>
                  <circle className="track" cx="60" cy="60" r="52" />
                  <circle className="arc" id="ringArc" cx="60" cy="60" r="52"
                    style={{ strokeDashoffset: S.ring.arcOffset || undefined, opacity: S.ring.arcOpacity || undefined }} />
                  {/* שובל שמקיף כל הזמן כל עוד עובדים — שרואים שהמערכת חיה */}
                  <circle className="orbit" cx="60" cy="60" r="44" />
                </svg>
                <div className="count">
                  <b id="ringNum">{S.ring.num}</b>
                  <span id="ringOf">{S.ring.of}</span>
                </div>
                <svg className="check" viewBox="0 0 52 52" aria-hidden="true"><path d="M14 27l8 8 16-17" /></svg>
              </div>
              <strong id="pTitle">{S.pTitle}</strong>
              <span id="pCount">{S.pCount}</span>
              <span id="pTime"></span>
            </div>
          </div>
        </div>
        <ul id="pFiles">
          {S.pFiles.map((f, i) => (
            <li key={i}><bdi>{f.name}</bdi>{f.error ? <> — <span className="bad">{f.error}</span></> : null}</li>
          ))}
        </ul>
      </section>
    </section>
  );
}

function ProgressTile({ tile }: { tile: { className: string; src: string } }) {
  const [broken, setBroken] = useState(false);
  return (
    <div className={tile.className}>
      <img alt="" src={tile.src || undefined} style={broken ? { visibility: 'hidden' } : undefined} onError={() => setBroken(true)} />
      <i className="dot"></i>
    </div>
  );
}
