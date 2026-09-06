from app.features.data_exchange.routes import data_exchange_bp


def register_blueprints(app):
    app.register_blueprint(data_exchange_bp)
