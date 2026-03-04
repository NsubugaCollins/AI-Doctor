from rest_framework import serializers
from .models import Consultation, Symptom, LabTest, Prescription, Patient
from apps.users.models import User

class PatientSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    
    class Meta:
        model = Patient
        fields = '__all__'

class SymptomSerializer(serializers.ModelSerializer):
    class Meta:
        model = Symptom
        fields = '__all__'

class LabTestSerializer(serializers.ModelSerializer):
    class Meta:
        model = LabTest
        fields = '__all__'

class PrescriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Prescription
        fields = '__all__'
class ConsultationSerializer(serializers.ModelSerializer):
    patient_details = PatientSerializer(source='patient', read_only=True)
    symptoms = SymptomSerializer(source='symptom_list', many=True, read_only=True)
    lab_tests = LabTestSerializer(source='lab_test_list', many=True, read_only=True)
    prescriptions = PrescriptionSerializer(source='prescription_list', many=True, read_only=True)

    # Ensure JSONB fields are never empty strings
    symptoms_data = serializers.JSONField(required=False, default=list)
    diagnosis_data = serializers.JSONField(required=False, default=dict)
    lab_tests_data = serializers.JSONField(required=False, default=list)
    prescription_data = serializers.JSONField(required=False, default=dict)

    class Meta:
        model = Consultation
        fields = '__all__'

    def create(self, validated_data):
        # Pop custom JSON fields if they exist
        symptoms_data = validated_data.pop('symptoms_data', [])
        diagnosis_data = validated_data.pop('diagnosis_data', {})
        lab_tests_data = validated_data.pop('lab_tests_data', [])
        prescription_data = validated_data.pop('prescription_data', {})

        consultation = Consultation.objects.create(
            **validated_data,
            symptoms=symptoms_data,
            diagnosis=diagnosis_data,
            lab_tests=lab_tests_data,
            prescription=prescription_data,
        )
        return consultation

class ConsultationStatusSerializer(serializers.Serializer):
    consultation_id = serializers.UUIDField()
    current_state = serializers.CharField()
    patient_name = serializers.CharField()
    has_symptoms = serializers.BooleanField()
    has_diagnosis = serializers.BooleanField()
    lab_tests_count = serializers.IntegerField()
    has_prescription = serializers.BooleanField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()