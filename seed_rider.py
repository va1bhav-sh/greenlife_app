from app import db, Rider, app

with app.app_context():
    if not Rider.query.filter_by(email='rider@example.com').first():
        r = Rider(name='Test Rider', email='rider@example.com', phone='9999999999')
        r.set_password('riderpass')
        db.session.add(r)
        db.session.commit()
        print('Rider created: rider@example.com / riderpass')
    else:
        print('Rider already exists.')
