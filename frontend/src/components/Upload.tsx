/* אזור: העלאת טפסים — שלבי העבודה, גרירה, והתקדמות חיה (גלגל אחוזים + אריחים). */
import { useRef, useState } from 'react';
import { S } from '../store';
import { upload } from '../actions';
import { Btn } from './Bits';

const STEPS = [['1', 'העלאה'], ['2', 'בדיקה ואישור'], ['3', 'ייצוא לאקסל']];

export function UploadStrip() {
  const file = useRef<HTMLInputElement>(null);
  const early = S.processing && S.resultsVisible;
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
        <HeroArt />
        <h3>גררו לכאן טפסים</h3>
        <p>או</p>
        <div className="actions">
          <Btn className="primary big" id="browse" onClick={(e) => { e.stopPropagation(); file.current?.click(); }}>בחירת קבצים</Btn>
        </div>
        <input type="file" id="file" ref={file} className="hidden" accept=".pdf,.jpg,.jpeg,.png" multiple
          onClick={(e) => e.stopPropagation()} onChange={(e) => upload(e.target.files)} />
        <small id="limits">{S.config ? 'PDF, JPG או PNG · עד ' + S.config.max_pages + ' טפסים בכל פעם' : 'PDF, JPG או PNG'}</small>
      </section>

      {/* התקדמות — בלי אחוזים (החלטת נועה, 21/10/2026). לפני הטופס הראשון: אנימציה של קליטה. מהטופס
          הראשון: פס דק בלי מספר, והאריחים האמיתיים (לחיצים) ישר מתחתיו. */}
      <section id="progress" className={'card' + (S.progressVisible ? '' : ' hidden') + (early ? ' early' : '')}
        aria-label="התקדמות הקליטה">
        {early ? (
          <div className="pbarwrap" role="status" aria-live="polite">
            <div className="pbar" role="progressbar" aria-label="התקדמות הקליטה" aria-valuemin={0} aria-valuemax={100}
              aria-valuenow={S.ring.shown}>
              <span style={{ width: Math.max(4, S.ring.shown) + '%' }}></span>
            </div>
            <p className="pbarnote"><strong id="pTitle">{S.pTitle}</strong> · <span id="pCount">{S.pCount}</span></p>
          </div>
        ) : (
          <div className="intakebox" role="status" aria-live="polite">
            <HeroArt className="hero intake" />
            <strong id="pTitle">{S.pTitle}</strong>
            <span id="pCount">{S.pCount}</span>
            <ul id="pFiles">
              {S.pFiles.map((f, i) => (
                <li key={i}><bdi>{f.name}</bdi>{f.error ? <> — <span className="bad">{f.error}</span></> : null}</li>
              ))}
            </ul>
          </div>
        )}
      </section>
    </section>
  );
}

// האיור: מסמכים ← חץ ← טבלה. במסך הגרירה הוא עומד; בזמן הקליטה (hero intake) המסמכים "נכנסים" לטבלה.
function HeroArt({ className = 'hero' }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 320 120" aria-hidden="true">
      <g className="sheets">
        <rect x="18" y="22" width="62" height="80" rx="6" className="sheet s3" />
        <rect x="30" y="14" width="62" height="80" rx="6" className="sheet s2" />
        <g className="s1g">
          <rect x="42" y="6" width="62" height="80" rx="6" className="sheet s1" />
          <path d="M54 26h38M54 38h30M54 50h38M54 62h22" className="ink" />
          <path d="M60 74h30" className="ink hand" />
        </g>
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
  );
}
