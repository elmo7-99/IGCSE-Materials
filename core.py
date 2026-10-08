"""IGCSE deterministic order engine. Python 3.11+, no runtime dependencies."""
import contextlib, hashlib, hmac, json, os, re, sqlite3, time, uuid
from pathlib import Path

class Invalid(ValueError): pass

def phone(value):
    value = str(value).translate(str.maketrans('٠١٢٣٤٥٦٧٨٩','0123456789'))
    n = re.sub(r'[\s()+-]', '', value)
    if n.startswith('00'): n = n[2:]
    if re.fullmatch(r'05\d{8}', n): n = '971' + n[1:]
    if not re.fullmatch(r'9715\d{8}', n): raise Invalid('Expected a UAE mobile number, e.g. 0551234567')
    return n

def bounded(value, name, maximum=1000):
    s = str(value or '').strip()
    if not s or len(s)>maximum: raise Invalid(f'{name} is required; maximum {maximum} characters')
    return s

class Engine:
    def __init__(self, db, config):
        self.db, self.config = str(db), config
        Path(self.db).parent.mkdir(parents=True, exist_ok=True)
        with self.conn() as c:
            c.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS orders(id TEXT PRIMARY KEY,source_id TEXT UNIQUE,phone TEXT,
            name TEXT,subject TEXT,teacher TEXT,requested TEXT,lang TEXT,city TEXT,state TEXT,
            sku TEXT,quantity INTEGER,books INTEGER,delivery INTEGER,total INTEGER,address TEXT,
            location TEXT,consent INTEGER,paused INTEGER DEFAULT 0,created REAL,updated REAL,last_inbound REAL DEFAULT 0,
            tracking TEXT,eta TEXT,unrecognized INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS inbox(id TEXT PRIMARY KEY,phone TEXT,received REAL);
            CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,order_id TEXT,event TEXT,data TEXT,at REAL);
            CREATE TABLE IF NOT EXISTS receipts(id TEXT PRIMARY KEY,order_id TEXT,media_id TEXT,mime TEXT,
            path TEXT,sha256 TEXT,status TEXT,reference TEXT UNIQUE,received REAL);
            CREATE TABLE IF NOT EXISTS outbox(id TEXT PRIMARY KEY,order_id TEXT,kind TEXT,body TEXT,image TEXT,
            state TEXT DEFAULT 'pending',provider_id TEXT,attempts INTEGER DEFAULT 0,next_try REAL DEFAULT 0,
            error TEXT,created REAL,claimed REAL);
            DROP INDEX IF EXISTS one_active_phone;
            CREATE TABLE IF NOT EXISTS sessions(phone TEXT PRIMARY KEY,order_id TEXT);
            CREATE TABLE IF NOT EXISTS workorders(order_id TEXT PRIMARY KEY,body TEXT,status TEXT,created REAL);
            ''')
            existing={r['name'] for r in c.execute('PRAGMA table_info(orders)')}
            for key in ('initial_address','school','student_phone'):
                if key not in existing: c.execute(f'ALTER TABLE orders ADD COLUMN {key} TEXT')
            existing={r['name'] for r in c.execute('PRAGMA table_info(outbox)')}
            if 'target_phone' not in existing: c.execute('ALTER TABLE outbox ADD COLUMN target_phone TEXT')
            if 'internal' not in existing: c.execute('ALTER TABLE outbox ADD COLUMN internal INTEGER DEFAULT 0')
    @contextlib.contextmanager
    def conn(self):
        c=sqlite3.connect(self.db,timeout=20); c.row_factory=sqlite3.Row
        try:
            c.execute('BEGIN IMMEDIATE'); yield c; c.commit()
        except Exception: c.rollback(); raise
        finally: c.close()
    def audit(self,c,oid,event,data=None):
        c.execute('INSERT INTO audit(order_id,event,data,at) VALUES(?,?,?,?)',
                  (oid,event,json.dumps(data or {},ensure_ascii=False),time.time()))
    def queue(self,c,o,kind,body,image=None):
        if not o['consent'] or o['paused']: return
        c.execute('INSERT INTO outbox(id,order_id,kind,body,image,created) VALUES(?,?,?,?,?,?)',
                  (uuid.uuid4().hex,o['id'],kind,body,image,time.time()))
    def get(self,c,oid):
        r=c.execute('SELECT * FROM orders WHERE id=?',(oid,)).fetchone()
        if not r: raise Invalid('Order not found')
        return dict(r)
    def set(self,c,o,state=None,**fields):
        if state: fields['state']=state
        fields['updated']=time.time()
        c.execute('UPDATE orders SET '+','.join(k+'=?' for k in fields)+' WHERE id=?',[*fields.values(),o['id']])
        o.update(fields)
    def say(self,o,ar,en): return ar if o['lang']=='ar' else en
    def choices(self,o):
        return [p for p in self.config['packages'] if p.get('active') and p.get('price_fils') is not None
                and p['subject'].casefold()==o['subject'].casefold()
                and (not o['teacher'] or p['teacher'].casefold()==o['teacher'].casefold())]
    def intro(self,c,o):
        ps=self.choices(o)
        if not ps:
            self.set(c,o,'REVIEW'); self.audit(c,o['id'],'catalog_missing'); return
        if o['requested'] in self.config.get('unpriced_requests',{}).get(o['subject'],[]):
            self.set(c,o,'REVIEW'); self.audit(c,o['id'],'requested_package_unpriced',{'requested':o['requested']})
            self.queue(c,o,'intro',self.say(o,f'مرحبًا {o["name"]}، استلمنا طلب {o["id"]} لكتب {o["subject"]} – {o["requested"]}. نراجع تفاصيل هذه الباقة وسعرها وسنتواصل معك للتأكيد قبل الدفع.',f'Hello {o["name"]}, we received order {o["id"]} for {o["subject"]} – {o["requested"]}. We are reviewing this package and its price, and will contact you to confirm before payment.'),ps[0].get('image_url'))
            return
        teachers={p['teacher'] for p in ps}
        if len(teachers)>1:
            self.set(c,o,'REVIEW'); self.audit(c,o['id'],'teacher_ambiguous'); return
        self.set(c,o,teacher=ps[0]['teacher'])
        options='\n'.join(f"{p['sku']} — {p['name']} — {p['price_fils']/100:.2f} AED" for p in ps)
        body=self.say(o,
            f"مرحبًا {o['name']}، معك النادي المصري – العين. طلبك {o['id']} لكتب {o['subject']} مع {o['teacher']}.\n{options}\nاختيارك المسجل: {o['requested']}. لتأكيد الباقة والكمية أرسل: CONFIRM رمز_الباقة الكمية\nمثال: CONFIRM {ps[0]['sku']} 1",
            f"Hello {o['name']}, Egyptian Club – Al Ain here. Order {o['id']}: {o['subject']} with {o['teacher']}.\n{options}\nYour registered choice: {o['requested']}. Reply: CONFIRM package_code quantity\nExample: CONFIRM {ps[0]['sku']} 1")
        images={p.get('image_url','') for p in ps}
        image=ps[0].get('image_url') if len(images)==1 else None
        # One catalog image per teacher is required before live activation.
        hint=self.say(o, f'يمكنك تحديد هذا الطلب بإرسال ORDER {o["id"]}.', f'To select this order, reply ORDER {o["id"]}.')
        suggested=self.config.get('request_aliases',{}).get(o['subject'],{}).get(o['requested'])
        if suggested:
            hint+=self.say(o,' أو أرسل تأكيد للموافقة على اختيارك المسجل ونسخة واحدة.',' Or reply CONFIRM to approve your registered choice, quantity one.')
        self.queue(c,o,'intro',body+'\n'+hint,image)
    def create(self,d):
        source=bounded(d.get('source_id'),'source_id',200)
        n=phone(d.get('phone')); name=bounded(d.get('name'),'name',150)
        subject=bounded(d.get('subject'),'subject',100); city=bounded(d.get('city'),'city',150)
        lang=d.get('lang','en')
        if lang not in ('ar','en'): raise Invalid('lang must be ar or en')
        if d.get('consent') is not True: raise Invalid('Explicit WhatsApp order-update consent is required')
        with self.conn() as c:
            old=c.execute('SELECT * FROM orders WHERE source_id=?',(source,)).fetchone()
            if old: return dict(old)
            now=time.time(); oid='IG-'+uuid.uuid4().hex[:10].upper()
            c.execute('''INSERT INTO orders(id,source_id,phone,name,subject,teacher,requested,lang,city,state,consent,created,updated)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                      (oid,source,n,name,subject,str(d.get('teacher','')).strip(),str(d.get('package','')).strip(),lang,city,'AWAIT_PACKAGE',1,now,now))
            o=self.get(c,oid)
            self.set(c,o,initial_address=str(d.get('initial_address','')).strip()[:1000],school=str(d.get('school','')).strip()[:200],student_phone=str(d.get('student_phone','')).strip()[:40])
            self.audit(c,oid,'registered'); self.intro(c,o); return o
    def confirm(self,c,o,sku,qty):
        if o['state']!='AWAIT_PACKAGE': raise Invalid('Package selection is not currently open')
        p=next((p for p in self.choices(o) if p['sku'].casefold()==str(sku).casefold()),None)
        if not p: raise Invalid('Choose a package code from the catalog for this subject and teacher')
        if type(qty)!=int or not 1<=qty<=50: raise Invalid('Quantity must be between 1 and 50')
        fee=self.config.get('delivery_fils',{}).get(o['city'])
        if type(fee)!=int or fee<0: raise Invalid('Delivery fee for this city must be configured by staff')
        books=p['price_fils']*qty
        self.set(c,o,'AWAIT_LOCATION',sku=p['sku'],quantity=qty,books=books,delivery=fee,total=books+fee)
        self.audit(c,o['id'],'package_confirmed',{'sku':sku,'quantity':qty,'total_fils':books+fee})
        if o.get('initial_address'):
            self.set(c,o,'AWAIT_ADDRESS_CONFIRM')
            saved=o['initial_address']
            self.queue(c,o,'location',self.say(o,
                f'طلب {o["id"]}: {p["name"]} × {qty}. الإجمالي شامل التوصيل {o["total"]/100:.2f} درهم. العنوان المسجل: {saved}. أرسل تأكيد إذا كان صحيحًا، أو أرسل العنوان والموقع المعدلين.',
                f'Order {o["id"]}: {p["name"]} × {qty}. Total including delivery AED {o["total"]/100:.2f}. Registered delivery address: {saved}. Reply CONFIRM if correct, or send your corrected address/location.'))
            return
        self.queue(c,o,'location',self.say(o,
          f"تم اختيار {p['name']} × {qty}. الكتب: {books/100:.2f} درهم؛ التوصيل: {fee/100:.2f}؛ الإجمالي: {(books+fee)/100:.2f} درهم. يرجى إرسال موقع التوصيل باستخدام مشاركة الموقع في واتساب.",
          f"Selected: {p['name']} × {qty}. Books: AED {books/100:.2f}; delivery: AED {fee/100:.2f}; total: AED {(books+fee)/100:.2f}. Please share your delivery location using WhatsApp's location feature."))
    def payment_request(self,c,o):
        bank=self.config.get('bank',{})
        if not all(bank.get(k) for k in ('name','holder','iban')):
            self.set(c,o,'REVIEW'); self.audit(c,o['id'],'bank_missing'); return
        self.set(c,o,'AWAIT_RECEIPT')
        b=f"{bank['name']}\n{bank['holder']}\nIBAN: {bank['iban']}"
        self.queue(c,o,'payment',self.say(o,
            f"تم تسجيل العنوان: {o['address']}. طلب {o['id']}، الإجمالي {o['total']/100:.2f} درهم. يرجى التحويل إلى:\n{b}\nأرسل صورة أو PDF لإيصال الدفع هنا. سنؤكد الدفع بعد التحقق من وصوله.",
            f"Address recorded: {o['address']}. Order {o['id']}, total AED {o['total']/100:.2f}. Please transfer to:\n{b}\nSend your payment receipt as an image or PDF here. Payment will be confirmed after checking receipt of funds."))
    def incoming(self,m):
        mid=bounded(m.get('id'),'message id',200); n=phone(m.get('from'))
        typ=m.get('type','text'); text=m.get('text',{}).get('body','').strip()
        if typ=='interactive':
            x=m.get('interactive',{}); text=(x.get('button_reply') or x.get('list_reply') or {}).get('id','')
        if typ=='button': text=m.get('button',{}).get('payload','')
        with self.conn() as c:
            if c.execute('SELECT 1 FROM inbox WHERE id=?',(mid,)).fetchone(): return {'duplicate':True}
            c.execute('INSERT INTO inbox VALUES(?,?,?)',(mid,n,time.time()))
            rs=[dict(r) for r in c.execute("SELECT * FROM orders WHERE phone=? AND state NOT IN ('DELIVERED','CANCELLED') ORDER BY created",(n,))]
            if not rs: return {'unmatched':True}
            if text.casefold() in ('stop','unsubscribe','إيقاف','ايقاف','توقف'):
                for o in rs:
                    self.set(c,o,consent=0,paused=1)
                    c.execute("UPDATE outbox SET state='cancelled' WHERE order_id=? AND internal=0 AND state IN ('pending','blocked')",(o['id'],))
                    self.audit(c,o['id'],'opt_out')
                return rs[0]
            if text.casefold() in ('human','staff','موظف','مساعدة'):
                for o in rs: self.set(c,o,paused=1); self.audit(c,o['id'],'human_requested')
                return rs[0]
            explicit=re.match(r'^(?:ORDER\s+)?(IG-[A-Z0-9]+)(?:\s+(.*))?$',text,re.I)
            selected=None
            if explicit:
                selected=next((x for x in rs if x['id'].casefold()==explicit[1].casefold()),None)
                if selected:
                    c.execute('INSERT OR REPLACE INTO sessions VALUES(?,?)',(n,selected['id']))
                    text=(explicit[2] or '').strip()
                    if not text:
                        self.queue(c,selected,'selected',self.say(selected,f'تم تحديد طلب {selected["id"]}: {selected["name"]} – {selected["subject"]}. أكمل الخطوة السابقة لهذا الطلب.',f'Order {selected["id"]} selected: {selected["name"]} – {selected["subject"]}. Please complete its previous step.'))
                        return selected
            if selected is None:
                if len(rs)==1: selected=rs[0]
                else:
                    session=c.execute('SELECT order_id FROM sessions WHERE phone=?',(n,)).fetchone()
                    if session: selected=next((x for x in rs if x['id']==session['order_id']),None)
            if selected is None:
                refs='; '.join(x['id']+' '+x['name']+' '+x['subject'] for x in rs)
                self.queue(c,rs[0],'select_order',self.say(rs[0],f'لديك عدة طلبات: {refs}. لتحديد الطلب أرسل ORDER ثم رقمه.',f'You have multiple orders: {refs}. Reply ORDER followed by the order number.'))
                return {'needs_order_selection':True}
            o=selected
            stamp=float(m.get('timestamp',time.time()))
            self.set(c,o,last_inbound=min(time.time(),stamp))
            if o['paused'] or not o['consent']: return o
            try:
                if o['state']=='AWAIT_PACKAGE':
                    if text.casefold() in ('confirm','تأكيد','تاكيد'):
                        suggested=self.config.get('request_aliases',{}).get(o['subject'],{}).get(o['requested'])
                        if suggested: text='CONFIRM '+suggested+' 1'
                    match=re.fullmatch(r'(?:CONFIRM|تأكيد|تاكيد)\s+([\w-]+)\s+(\d+)',text,re.I)
                    if not match: raise Invalid('Reply CONFIRM package_code quantity / تأكيد رمز_الباقة الكمية')
                    self.confirm(c,o,match[1],int(match[2]))
                elif o['state']=='AWAIT_ADDRESS_CONFIRM':
                    if typ=='location':
                        loc=m.get('location',{}); lat,lon=loc.get('latitude'),loc.get('longitude')
                        if not isinstance(lat,(int,float)) or not isinstance(lon,(int,float)) or not -90<=lat<=90 or not -180<=lon<=180: raise Invalid('Invalid location')
                        self.set(c,o,'AWAIT_ADDRESS',location=json.dumps({'latitude':lat,'longitude':lon}))
                        self.queue(c,o,'address',self.say(o,'أرسل اسم المنطقة والمبنى ورقم الشقة.','Please send the area, building and apartment number.'))
                    else:
                        if typ!='text': raise Invalid('Please confirm or correct your address / يرجى تأكيد أو تصحيح العنوان')
                        saved=o['initial_address']
                        addr=saved if text.casefold() in ('confirm','تأكيد','تاكيد') else bounded(text,'address',500)
                        self.set(c,o,address=addr)
                        if re.fullmatch(r'https?://\S+',addr):
                            self.set(c,o,'AWAIT_ADDRESS',location=json.dumps({'map_url':addr}))
                            self.queue(c,o,'address',self.say(o,'تم تأكيد الموقع. أرسل اسم المبنى ورقم الشقة لاستكمال العنوان.','Location confirmed. Please send the building and apartment number to complete your address.'))
                        else: self.payment_request(c,o)
                elif o['state']=='AWAIT_LOCATION':
                    loc=m.get('location',{})
                    if typ!='location': raise Invalid('Please share a WhatsApp location / يرجى مشاركة موقع واتساب')
                    lat,lon=loc.get('latitude'),loc.get('longitude')
                    if not isinstance(lat,(int,float)) or not isinstance(lon,(int,float)) or not -90<=lat<=90 or not -180<=lon<=180:
                        raise Invalid('Invalid location')
                    self.set(c,o,'AWAIT_ADDRESS',location=json.dumps({'latitude':lat,'longitude':lon}))
                    self.queue(c,o,'address',self.say(o,'تم استلام الموقع. أرسل اسم المنطقة والمبنى ورقم الشقة في رسالة واحدة.','Location received. Please send the area, building and apartment number in one message.'))
                elif o['state']=='AWAIT_ADDRESS':
                    if typ!='text': raise Invalid('Please send the address as text / أرسل العنوان كتابةً')
                    self.set(c,o,address=bounded(text,'address',500)); self.payment_request(c,o)
                elif o['state']=='AWAIT_RECEIPT':
                    if typ not in ('image','document'): raise Invalid('Please send a receipt image or PDF / أرسل صورة الإيصال أو PDF')
                    media=m.get(typ,{})
                    mime=media.get('mime_type','image/jpeg' if typ=='image' else '')
                    if mime not in ('image/jpeg','image/png','application/pdf'): raise Invalid('Only JPEG, PNG or PDF receipts are supported')
                    rid=uuid.uuid4().hex
                    c.execute('INSERT INTO receipts(id,order_id,media_id,mime,status,received) VALUES(?,?,?,?,?,?)',
                              (rid,o['id'],bounded(media.get('id'),'media id',200),mime,'received',time.time()))
                    self.set(c,o,'PAYMENT_REVIEW'); self.audit(c,o['id'],'receipt_received',{'receipt_id':rid})
                    self.queue(c,o,'receipt',self.say(o,'تم استلام إيصال الدفع، وجارٍ التحقق من وصول المبلغ. سنرسل تأكيد تجهيز الطلب بعد المراجعة.','Payment receipt received. We are checking receipt of funds and will confirm order preparation after review.'))
                else:
                    self.audit(c,o['id'],'followup_received',{'type':typ})
                    return o
                self.set(c,o,unrecognized=0)
            except Invalid as e:
                count=o['unrecognized']+1; self.set(c,o,unrecognized=count)
                self.queue(c,o,'help',str(e))
                if count>=3:
                    self.set(c,o,paused=1); self.audit(c,o['id'],'human_review_needed')
            return o
    def action(self,oid,action,d):
        with self.conn() as c:
            o=self.get(c,oid)
            if action=='approve_payment':
                if o['state']!='PAYMENT_REVIEW': raise Invalid('Order must be awaiting payment review')
                if d.get('funds_verified') is not True: raise Invalid('Verify funds in the bank before approval')
                ref=bounded(d.get('bank_reference'),'bank_reference',200)
                r=c.execute('SELECT * FROM receipts WHERE order_id=? ORDER BY received DESC LIMIT 1',(oid,)).fetchone()
                if not r: raise Invalid('No receipt recorded')
                if c.execute('SELECT 1 FROM receipts WHERE reference=?',(ref,)).fetchone(): raise Invalid('Bank reference has already been used')
                c.execute("UPDATE receipts SET status='approved',reference=? WHERE id=?",(ref,r['id']))
                self.set(c,o,'PREPARING'); self.audit(c,oid,'funds_verified',{'bank_reference':ref})
                self.make_workorder(c,o)
                self.queue(c,o,'paid',self.say(o,f"تم تأكيد الدفع لطلب {oid} ✅ جارٍ تجهيز كتبك، وسنرسل موعد التوصيل عند الشحن.",f"Payment confirmed for order {oid} ✅ Your books are being prepared. We will send delivery details when dispatched."))
            elif action=='reject_payment':
                if o['state']!='PAYMENT_REVIEW': raise Invalid('Order must be awaiting payment review')
                reason=bounded(d.get('reason'),'reason',300)
                c.execute("UPDATE receipts SET status='rejected' WHERE order_id=? AND status='received'",(oid,))
                self.set(c,o,'AWAIT_RECEIPT'); self.audit(c,oid,'receipt_rejected',{'reason':reason})
                self.queue(c,o,'rejected',self.say(o,f"نحتاج مراجعة إيصال الدفع: {reason}. يرجى إرسال الإيصال الصحيح.",f"We need to review your payment receipt: {reason}. Please send the correct receipt."))
            elif action in ('mark_printed','mark_packed'):
                if o['state']!='PREPARING': raise Invalid('Payment approval is required before production')
                job=c.execute('SELECT status FROM workorders WHERE order_id=?',(oid,)).fetchone()
                expected='READY' if action=='mark_printed' else 'PRINTED'
                if not job or job['status']!=expected: raise Invalid('Complete the previous production stage first')
                status='PRINTED' if action=='mark_printed' else 'PACKED'
                c.execute('UPDATE workorders SET status=? WHERE order_id=?',(status,oid))
                self.audit(c,oid,'production_'+status.lower())
            elif action=='dispatch':
                if o['state']!='PREPARING': raise Invalid('Payment approval is required before dispatch')
                if self.config.get('require_packing_confirmation'):
                    job=c.execute('SELECT status FROM workorders WHERE order_id=?',(oid,)).fetchone()
                    if not job or job['status']!='PACKED': raise Invalid('Confirm printing and packing before dispatch')
                eta=bounded(d.get('eta'),'eta',200); tracking=bounded(d.get('tracking'),'tracking',200)
                self.set(c,o,'SHIPPED',eta=eta,tracking=tracking); self.audit(c,oid,'dispatched',{'tracking':tracking,'eta':eta})
                self.queue(c,o,'shipping',self.say(o,f"تم شحن طلب {oid} ✅ موعد التوصيل المتوقع: {eta}. مرجع الشحنة: {tracking}. يرجى إبقاء هاتفك متاحًا للاستلام.",f"Order {oid} dispatched ✅ Expected delivery: {eta}. Shipment reference: {tracking}. Please keep your phone available to receive it."))
            elif action=='deliver':
                if o['state']!='SHIPPED': raise Invalid('Order must be shipped first')
                proof=bounded(d.get('proof'),'delivery proof',300)
                self.set(c,o,'DELIVERED'); self.audit(c,oid,'delivered',{'proof':proof})
                self.queue(c,o,'delivered',self.say(o,f"تم تسجيل تسليم طلب {oid}. شكرًا لاختيارك النادي المصري – العين 🌷 إذا لم تستلم الطلب، يرجى التواصل معنا.",f"Order {oid} marked as delivered. Thank you for choosing Egyptian Club – Al Ain 🌷 Please contact us if you have not received it."))
            elif action=='cancel':
                if o['state'] in ('DELIVERED','CANCELLED'): raise Invalid('Order is already closed')
                reason=bounded(d.get('reason'),'reason',300)
                self.set(c,o,'CANCELLED',paused=1)
                c.execute("UPDATE outbox SET state='cancelled' WHERE order_id=? AND state IN ('pending','blocked')",(oid,))
                self.audit(c,oid,'cancelled',{'reason':reason})
            elif action=='pause': self.set(c,o,paused=1); self.audit(c,oid,'paused')
            elif action=='resume':
                if not o['consent']: raise Invalid('Customer opted out; renewed consent is required')
                self.set(c,o,paused=0); self.audit(c,oid,'resumed')
            elif action=='retry_catalog':
                if o['state']!='REVIEW': raise Invalid('Order must be in REVIEW')
                if d.get('teacher'): self.set(c,o,teacher=bounded(d['teacher'],'teacher',150))
                self.set(c,o,'AWAIT_PACKAGE'); self.intro(c,o)
            elif action=='retry_message':
                mid=bounded(d.get('message_id'),'message_id',100)
                # Uncertain sends require manual provider reconciliation before any retry.
                if d.get('provider_checked') is not True: raise Invalid('Reconcile provider delivery before retry')
                c.execute("UPDATE outbox SET state='pending',next_try=0,error=NULL WHERE id=? AND order_id=? AND state IN ('blocked','failed','uncertain')",(mid,oid))
                self.audit(c,oid,'message_retry',{'message_id':mid})
            else: raise Invalid('Unknown action')
            return o
    def make_workorder(self,c,o):
        p=next(x for x in self.config['packages'] if x['sku']==o['sku'])
        body=(f"أمر تجهيز {o['id']} | الدفع معتمد\nالطالب: {o['name']}\nالمادة: {o['subject']} | المدرّس: {o['teacher']}\n"
              f"الباقة: {p['name']} ({p['sku']}) | الكمية: {o['quantity']}\n"
              f"الكتب: {p.get('books','راجع ملف الباقة')} لكل باقة | الصفحات: {p.get('pages','راجع ملف الباقة')} لكل باقة\n"
              f"الطباعة: طبق ملفات الباقة ومواصفاتها المعتمدة؛ لا تفترض ألوانًا أو عدد نسخ مختلفًا.\n"
              f"التغليف: اجمع الكتب حسب الباقة وأرفق ملصق رقم الطلب والطالب.\n"
              f"التوصيل: {o['city']} | {o['address']}\nالموقع: {o['location'] or o.get('initial_address') or ''}\n"
              f"هاتف الاستلام: {o['phone']} | الإجمالي المدفوع: {o['total']/100:.2f} درهم")
        c.execute('INSERT OR IGNORE INTO workorders VALUES(?,?,?,?)',(o['id'],body,'READY',time.time()))
        seen=set()
        for role,recipient in self.config.get('internal_recipients',{}).items():
            if not recipient: continue
            n=phone(recipient)
            if n in seen: continue
            seen.add(n)
            c.execute('INSERT INTO outbox(id,order_id,kind,body,target_phone,internal,created) VALUES(?,?,?,?,?,1,?)',
                      (uuid.uuid4().hex,o['id'],'workorder',body,n,time.time()))
        self.audit(c,o['id'],'workorder_ready',{'internal_recipient_count':len(seen)})
    def list(self):
        with self.conn() as c: return [dict(r) for r in c.execute('SELECT * FROM orders ORDER BY created DESC')]
    def details(self,oid):
        with self.conn() as c:
            o=self.get(c,oid)
            for table in ('receipts','audit','outbox','workorders'):
                o[table]=[dict(r) for r in c.execute(f'SELECT * FROM {table} WHERE order_id=?',(oid,))]
            return o
    def claim(self):
        with self.conn() as c:
            # A crashed worker may have sent; do not resend automatically.
            c.execute("UPDATE outbox SET state='uncertain',error='Worker interrupted; reconcile with provider' WHERE state='sending' AND claimed<?",(time.time()-120,))
            r=c.execute("""SELECT q.* FROM outbox q JOIN orders o ON q.order_id=o.id
            WHERE q.state='pending' AND q.next_try<=? AND (q.internal=1 OR (o.consent=1 AND o.paused=0))
            AND NOT EXISTS(SELECT 1 FROM outbox earlier WHERE earlier.order_id=q.order_id
            AND earlier.internal=q.internal AND COALESCE(earlier.target_phone,'')=COALESCE(q.target_phone,'')
            AND earlier.created<q.created AND earlier.state IN ('pending','sending','blocked','failed','uncertain'))
            ORDER BY q.created LIMIT 1""",(time.time(),)).fetchone()
            if not r: return None
            r=dict(r)
            c.execute("UPDATE outbox SET state='sending',claimed=?,attempts=attempts+1 WHERE id=?",(time.time(),r['id']))
            r['order']=self.get(c,r['order_id'])
            if r.get('target_phone'): r['order']['phone']=r['target_phone']; r['order']['lang']='ar'; r['order']['last_inbound']=0
            return r
    def finish(self,mid,state,error=None,provider_id=None):
        with self.conn() as c:
            c.execute('UPDATE outbox SET state=?,error=?,provider_id=? WHERE id=?',(state,error,provider_id,mid))
    def reminder(self):
        with self.conn() as c:
            rs=c.execute("SELECT * FROM orders WHERE state IN ('AWAIT_PACKAGE','AWAIT_LOCATION','AWAIT_ADDRESS','AWAIT_ADDRESS_CONFIRM','AWAIT_RECEIPT') AND updated<? AND consent=1 AND paused=0",(time.time()-86400,)).fetchall()
            count=0
            for r in rs:
                o=dict(r)
                if c.execute("SELECT 1 FROM audit WHERE order_id=? AND event='reminder'",(o['id'],)).fetchone(): continue
                self.queue(c,o,'reminder',self.say(o,f"تذكير بخصوص طلب {o['id']}: يرجى استكمال الخطوة السابقة لتجهيز كتبك. للمساعدة أرسل موظف، ولإيقاف التحديثات أرسل إيقاف.",f"Reminder for order {o['id']}: please complete the previous step so we can prepare your books. Reply STAFF for help or STOP to stop updates."))
                self.audit(c,o['id'],'reminder'); count+=1
            return count

def validate_config(cfg):
    if not isinstance(cfg,dict) or not isinstance(cfg.get('packages'),list): raise Invalid('Config must contain a packages array')
    for field in ('bank','delivery_fils','templates','internal_recipients','request_aliases','unpriced_requests'):
        if field in cfg and not isinstance(cfg[field],dict): raise Invalid(field+' must be an object')
    for fee in cfg.get('delivery_fils',{}).values():
        if type(fee)!=int or fee<0: raise Invalid('Delivery fees must be nonnegative integers in fils')
    seen=set()
    for p in cfg.get('packages',[]):
        if not isinstance(p,dict): raise Invalid('Every package must be an object')
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,40}',p.get('sku','')) or p['sku'].casefold() in seen: raise Invalid('Invalid or duplicate SKU')
        seen.add(p['sku'].casefold())
        for k in ('name','teacher','subject'): bounded(p.get(k),k,150)
        if p.get('active') and (type(p.get('price_fils'))!=int or p['price_fils']<0): raise Invalid('Active packages require a nonnegative integer price_fils')
    for recipient in cfg.get('internal_recipients',{}).values():
        if recipient: phone(recipient)
    return cfg
