# color_dialog.py
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QSlider, QPushButton, QGroupBox)
from PyQt6.QtCore import Qt, pyqtSignal

class ColorCorrectionDialog(QDialog):
    """Dialog for adjusting video color properties"""
    
    # Signals to communicate changes back to main player
    brightness_changed = pyqtSignal(int)
    contrast_changed = pyqtSignal(int)
    saturation_changed = pyqtSignal(int)
    gamma_changed = pyqtSignal(int)
    sharpness_changed = pyqtSignal(int)
    reset_all = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Color Correction")
        self.setModal(False)  # Non-modal so you can adjust while watching
        self.setMinimumWidth(400)
        
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        
        # Create adjustment group
        adjustments_group = QGroupBox("Video Adjustments")
        adjustments_layout = QVBoxLayout()
        
        # Brightness control (-100 to 100, default 0)
        brightness_layout = QHBoxLayout()
        brightness_layout.addWidget(QLabel("Brightness:"))
        self.brightness_slider = QSlider(Qt.Orientation.Horizontal)
        self.brightness_slider.setRange(-100, 100)
        self.brightness_slider.setValue(0)
        self.brightness_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.brightness_slider.setTickInterval(25)
        self.brightness_slider.valueChanged.connect(self.on_brightness_changed)
        brightness_layout.addWidget(self.brightness_slider)
        self.brightness_label = QLabel("0")
        self.brightness_label.setMinimumWidth(40)
        brightness_layout.addWidget(self.brightness_label)
        adjustments_layout.addLayout(brightness_layout)
        
        # Contrast control (-100 to 100, default 0)
        contrast_layout = QHBoxLayout()
        contrast_layout.addWidget(QLabel("Contrast:"))
        self.contrast_slider = QSlider(Qt.Orientation.Horizontal)
        self.contrast_slider.setRange(-100, 100)
        self.contrast_slider.setValue(0)
        self.contrast_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.contrast_slider.setTickInterval(25)
        self.contrast_slider.valueChanged.connect(self.on_contrast_changed)
        contrast_layout.addWidget(self.contrast_slider)
        self.contrast_label = QLabel("0")
        self.contrast_label.setMinimumWidth(40)
        contrast_layout.addWidget(self.contrast_label)
        adjustments_layout.addLayout(contrast_layout)
        
        # Saturation control (-100 to 100, default 0)
        saturation_layout = QHBoxLayout()
        saturation_layout.addWidget(QLabel("Saturation:"))
        self.saturation_slider = QSlider(Qt.Orientation.Horizontal)
        self.saturation_slider.setRange(-100, 100)
        self.saturation_slider.setValue(0)
        self.saturation_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.saturation_slider.setTickInterval(25)
        self.saturation_slider.valueChanged.connect(self.on_saturation_changed)
        saturation_layout.addWidget(self.saturation_slider)
        self.saturation_label = QLabel("0")
        self.saturation_label.setMinimumWidth(40)
        saturation_layout.addWidget(self.saturation_label)
        adjustments_layout.addLayout(saturation_layout)
        
        # Gamma control (-100 to 100, default 0)
        gamma_layout = QHBoxLayout()
        gamma_layout.addWidget(QLabel("Gamma:"))
        self.gamma_slider = QSlider(Qt.Orientation.Horizontal)
        self.gamma_slider.setRange(-100, 100)
        self.gamma_slider.setValue(0)
        self.gamma_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.gamma_slider.setTickInterval(25)
        self.gamma_slider.valueChanged.connect(self.on_gamma_changed)
        gamma_layout.addWidget(self.gamma_slider)
        self.gamma_label = QLabel("0")
        self.gamma_label.setMinimumWidth(40)
        gamma_layout.addWidget(self.gamma_label)
        adjustments_layout.addLayout(gamma_layout)
        
        # Sharpness control (0 to 100, default 0)
        sharpness_layout = QHBoxLayout()
        sharpness_layout.addWidget(QLabel("Sharpness:"))
        self.sharpness_slider = QSlider(Qt.Orientation.Horizontal)
        self.sharpness_slider.setRange(0, 100)
        self.sharpness_slider.setValue(0)
        self.sharpness_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.sharpness_slider.setTickInterval(25)
        self.sharpness_slider.valueChanged.connect(self.on_sharpness_changed)
        sharpness_layout.addWidget(self.sharpness_slider)
        self.sharpness_label = QLabel("0")
        self.sharpness_label.setMinimumWidth(40)
        sharpness_layout.addWidget(self.sharpness_label)
        adjustments_layout.addLayout(sharpness_layout)
        
        adjustments_group.setLayout(adjustments_layout)
        layout.addWidget(adjustments_group)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        reset_button = QPushButton("Reset All")
        reset_button.clicked.connect(self.on_reset_all)
        button_layout.addWidget(reset_button)
        
        button_layout.addStretch()
        
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.close)
        button_layout.addWidget(close_button)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def on_brightness_changed(self, value):
        self.brightness_label.setText(str(value))
        self.brightness_changed.emit(value)
    
    def on_contrast_changed(self, value):
        self.contrast_label.setText(str(value))
        self.contrast_changed.emit(value)
    
    def on_saturation_changed(self, value):
        self.saturation_label.setText(str(value))
        self.saturation_changed.emit(value)
    
    def on_gamma_changed(self, value):
        self.gamma_label.setText(str(value))
        self.gamma_changed.emit(value)
    
    def on_sharpness_changed(self, value):
        self.sharpness_label.setText(str(value))
        self.sharpness_changed.emit(value)
    
    def on_reset_all(self):
        """Reset all sliders to default values"""
        self.brightness_slider.setValue(0)
        self.contrast_slider.setValue(0)
        self.saturation_slider.setValue(0)
        self.gamma_slider.setValue(0)
        self.sharpness_slider.setValue(0)
        self.reset_all.emit()
    
    def get_values(self):
        """Get current values of all adjustments"""
        return {
            'brightness': self.brightness_slider.value(),
            'contrast': self.contrast_slider.value(),
            'saturation': self.saturation_slider.value(),
            'gamma': self.gamma_slider.value(),
            'sharpness': self.sharpness_slider.value()
        }
    
    def set_values(self, brightness=0, contrast=0, saturation=0, gamma=0, sharpness=0):
        """Set values for all adjustments"""
        self.brightness_slider.setValue(brightness)
        self.contrast_slider.setValue(contrast)
        self.saturation_slider.setValue(saturation)
        self.gamma_slider.setValue(gamma)
        self.sharpness_slider.setValue(sharpness)