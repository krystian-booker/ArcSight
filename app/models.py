from .extensions import db


class Setting(db.Model):
    __tablename__ = "settings"
    key = db.Column(db.String, primary_key=True)
    value = db.Column(db.String, nullable=False)

    def to_dict(self):
        return {"key": self.key, "value": self.value}


class Camera(db.Model):
    __tablename__ = "cameras"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    camera_type = db.Column(db.String, nullable=False)
    identifier = db.Column(db.String, unique=True, nullable=False)
    orientation = db.Column(db.Integer, default=0)
    exposure_value = db.Column(db.Integer, default=500)
    gain_value = db.Column(db.Integer, default=50)
    exposure_mode = db.Column(db.String, default="auto")
    gain_mode = db.Column(db.String, default="auto")
    camera_matrix_json = db.Column(db.String, nullable=True)
    dist_coeffs_json = db.Column(db.String, nullable=True)
    reprojection_error = db.Column(db.Float, nullable=True)
    device_info_json = db.Column(
        db.String, nullable=True
    )  # Stores USB VID/PID/Serial metadata

    pipelines = db.relationship(
        "Pipeline", back_populates="camera", cascade="all, delete-orphan"
    )

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "camera_type": self.camera_type,
            "identifier": self.identifier,
            "orientation": self.orientation,
            "exposure_value": self.exposure_value,
            "gain_value": self.gain_value,
            "exposure_mode": self.exposure_mode,
            "gain_mode": self.gain_mode,
            "camera_matrix_json": self.camera_matrix_json,
            "dist_coeffs_json": self.dist_coeffs_json,
            "reprojection_error": self.reprojection_error,
            "device_info_json": self.device_info_json,
        }


class Pipeline(db.Model):
    __tablename__ = "pipelines"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    pipeline_type = db.Column(db.String, nullable=False, default="AprilTag")
    config = db.Column(db.String)
    camera_id = db.Column(db.Integer, db.ForeignKey("cameras.id"), nullable=False)

    camera = db.relationship("Camera", back_populates="pipelines")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "pipeline_type": self.pipeline_type,
            "config": self.config,
            "camera_id": self.camera_id,
        }
