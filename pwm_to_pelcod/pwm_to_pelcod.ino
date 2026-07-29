#include <Arduino.h>
#include <SoftwareSerial.h>

// ---------------------------------------------------------
// Adjust these pins if your wiring is different
#define PAN_PWM_PIN   A2
#define TILT_PWM_PIN  A3
#define ZOOM_PWM_PIN  A4

// SoftwareSerial for Pelco-D output (pin 6=RX not used, pin 7=TX to camera)
SoftwareSerial pelcoSerial(6, 7);

// Pelco-D function codes for setting absolute values
#define PELCO_SET_PAN   0x4B
#define PELCO_SET_TILT  0x4D
#define PELCO_SET_ZOOM  0x4F

// Address of your camera (commonly 0x01)
#define CAMERA_ADDRESS  0x01

// Build and send a Pelco-D packet:
// [0] = 0xFF
// [1] = address
// [2] = command1 (0x00 for these SET commands)
// [3] = command2 (function code, e.g. 0x4B = SET-PAN)
// [4] = data1 (MSB)
// [5] = data2 (LSB)
// [6] = checksum = low 8 bits of sum(bytes[1..5])
void sendPelcoD(byte address, byte command2, int value) {
  // Break `value` (0..some max) into two bytes
  byte msb = (value >> 8) & 0xFF;
  byte lsb = value & 0xFF;

  // Build the frame
  byte packet[7];
  packet[0] = 0xFF;            // Sync
  packet[1] = address;         // Camera address
  packet[2] = 0x00;            // command1 (always 0x00 here)
  packet[3] = command2;        // command2 (SET-PAN, SET-TILT, or SET-ZOOM)
  packet[4] = msb;             // Data1
  packet[5] = lsb;             // Data2

  // Calculate checksum = sum of [address..lsb] mod 256
  byte sum = (packet[1] + packet[2] + packet[3] + packet[4] + packet[5]) & 0xFF;
  packet[6] = sum;

  // Send out via SoftwareSerial
  pelcoSerial.write(packet, 7);

}

void setup() {
  // Pins for PWM input
  pinMode(PAN_PWM_PIN,  INPUT);
  pinMode(TILT_PWM_PIN, INPUT);
  pinMode(ZOOM_PWM_PIN, INPUT);

  // Start built-in Serial (for debugging, if needed)
  Serial.begin(9600);
  
  // Start SoftwareSerial for Pelco-D at 9600 baud
  pelcoSerial.begin(9600);
}

void loop() {
  // Read incoming PWM pulse widths on pan/tilt/zoom (timeout 25 ms)
  unsigned long panPulse  = pulseIn(PAN_PWM_PIN,  HIGH, 25000);
  unsigned long tiltPulse = pulseIn(TILT_PWM_PIN, HIGH, 25000);
  unsigned long zoomPulse = pulseIn(ZOOM_PWM_PIN, HIGH, 25000);
  Serial.print("PAN ");
  Serial.print(panPulse);
  Serial.print(" TILT ");
  Serial.println(tiltPulse);

  // Only process if pulse is between 900 and 2100 microseconds
  // Otherwise ignore (could be no signal)
  if (panPulse >= 900 && panPulse <= 2100) {
    // Convert pulse to 0..35999 range (for 0..359.99°).
    int panValue = map(panPulse, 900, 2000, 0, 35999);
    Serial.print("PELCO_SET_PAN ");
    Serial.println(panValue);
    sendPelcoD(CAMERA_ADDRESS, PELCO_SET_PAN, panValue);
    delay(100);
  }

  if (tiltPulse >= 900 && tiltPulse <= 2100) {
    // Convert pulse to 0..8999 range (for 0..89.99°).
    int tiltValue = map(tiltPulse, 900, 2000, 0, 8999);
    Serial.print("PELCO_SET_TILT ");
    Serial.println(tiltValue);
    sendPelcoD(CAMERA_ADDRESS, PELCO_SET_TILT, tiltValue);
    delay(100);
  }

  if (zoomPulse >= 900 && zoomPulse <= 2100) {
    // Convert pulse to 0..2000 range (as in your original script).
    int zoomValue = map(zoomPulse, 900, 2100, 0, 2000);
    sendPelcoD(CAMERA_ADDRESS, PELCO_SET_ZOOM, zoomValue);
    delay(10);
  }

  delay(100); // Short delay to avoid spamming
}
