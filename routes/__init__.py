def register_blueprints(app):
    from .auth import auth_bp
    from .groups import groups_bp
    from .expenses import expenses_bp
    from .settlements import settlements_bp
    from .budgets import budgets_bp
    from .analytics import analytics_bp
    from .dashboard import dashboard_bp
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(groups_bp, url_prefix='/api/groups')
    app.register_blueprint(expenses_bp, url_prefix='/api/expenses')
    app.register_blueprint(settlements_bp, url_prefix='/api/settlements')
    app.register_blueprint(budgets_bp, url_prefix='/api/budgets')
    app.register_blueprint(analytics_bp, url_prefix='/api/analytics')
    app.register_blueprint(dashboard_bp, url_prefix='/api/dashboard')