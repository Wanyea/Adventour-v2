import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  FlatList,
  Alert,
  TextInput,
  Modal,
  ScrollView,
} from 'react-native';
import axios from 'axios';
import Config from '../src/Config';

interface Friend {
  id: number;
  username: string;
  display_name: string;
  profile_picture?: string;
  friendship_id: number;
  friendship_date: string;
}

interface Trip {
  id: number;
  name: string;
  description?: string;
  destination?: string;
  start_date?: string;
  end_date?: string;
  role: string;
  member_count: number;
  created_at: string;
}

interface FriendRequest {
  friendship_id: number;
  user_id: number;
  username: string;
  display_name: string;
  profile_picture?: string;
  request_date: string;
}

const SocialScreen: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'friends' | 'trips'>('friends');
  const [friends, setFriends] = useState<Friend[]>([]);
  const [trips, setTrips] = useState<Trip[]>([]);
  const [friendRequests, setFriendRequests] = useState<FriendRequest[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [showSearchModal, setShowSearchModal] = useState(false);
  const [showCreateTripModal, setShowCreateTripModal] = useState(false);
  const [newTripData, setNewTripData] = useState({
    name: '',
    description: '',
    destination: '',
    start_date: '',
    end_date: '',
  });

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      if (activeTab === 'friends') {
        const [friendsResponse, requestsResponse] = await Promise.all([
          axios.get(`${Config.BACKEND_BASE_URL}/api/friends`),
          axios.get(`${Config.BACKEND_BASE_URL}/api/friends/requests`),
        ]);
        setFriends(friendsResponse.data.friends);
        setFriendRequests(requestsResponse.data.requests);
      } else {
        const tripsResponse = await axios.get(`${Config.BACKEND_BASE_URL}/api/trips`);
        setTrips(tripsResponse.data.trips);
      }
    } catch (error) {
      console.error('Error loading data:', error);
      Alert.alert('Error', 'Failed to load data');
    }
  };

  const searchUsers = async () => {
    if (searchQuery.length < 2) return;

    try {
      const response = await axios.get(
        `${Config.BACKEND_BASE_URL}/api/friends/search?q=${encodeURIComponent(searchQuery)}`
      );
      setSearchResults(response.data.users);
    } catch (error) {
      console.error('Error searching users:', error);
      Alert.alert('Error', 'Failed to search users');
    }
  };

  const sendFriendRequest = async (friendId: number) => {
    try {
      await axios.post(`${Config.BACKEND_BASE_URL}/api/friends/request`, {
        friend_id: friendId,
      });
      Alert.alert('Success', 'Friend request sent!');
      setShowSearchModal(false);
      setSearchQuery('');
      setSearchResults([]);
    } catch (error: any) {
      Alert.alert('Error', error.response?.data?.error || 'Failed to send friend request');
    }
  };

  const respondToFriendRequest = async (friendshipId: number, action: 'accept' | 'reject') => {
    try {
      await axios.post(`${Config.BACKEND_BASE_URL}/api/friends/respond`, {
        friendship_id: friendshipId,
        action,
      });
      Alert.alert('Success', `Friend request ${action}ed!`);
      loadData();
    } catch (error: any) {
      Alert.alert('Error', error.response?.data?.error || 'Failed to respond to request');
    }
  };

  const createTrip = async () => {
    if (!newTripData.name) {
      Alert.alert('Error', 'Trip name is required');
      return;
    }

    try {
      await axios.post(`${Config.BACKEND_BASE_URL}/api/trips`, newTripData);
      Alert.alert('Success', 'Trip created successfully!');
      setShowCreateTripModal(false);
      setNewTripData({ name: '', description: '', destination: '', start_date: '', end_date: '' });
      loadData();
    } catch (error: any) {
      Alert.alert('Error', error.response?.data?.error || 'Failed to create trip');
    }
  };

  const renderFriend = ({ item }: { item: Friend }) => (
    <View style={styles.friendItem}>
      <View style={styles.friendInfo}>
        <Text style={styles.friendName}>{item.display_name}</Text>
        <Text style={styles.friendUsername}>@{item.username}</Text>
      </View>
      <Text style={styles.friendDate}>
        Friends since {new Date(item.friendship_date).toLocaleDateString()}
      </Text>
    </View>
  );

  const renderTrip = ({ item }: { item: Trip }) => (
    <View style={styles.tripItem}>
      <View style={styles.tripHeader}>
        <Text style={styles.tripName}>{item.name}</Text>
        <Text style={styles.tripRole}>{item.role}</Text>
      </View>
      {item.description && <Text style={styles.tripDescription}>{item.description}</Text>}
      {item.destination && <Text style={styles.tripDestination}>📍 {item.destination}</Text>}
      <View style={styles.tripFooter}>
        <Text style={styles.tripMembers}>{item.member_count} members</Text>
        <Text style={styles.tripDate}>
          {new Date(item.created_at).toLocaleDateString()}
        </Text>
      </View>
    </View>
  );

  const renderFriendRequest = ({ item }: { item: FriendRequest }) => (
    <View style={styles.requestItem}>
      <View style={styles.requestInfo}>
        <Text style={styles.requestName}>{item.display_name}</Text>
        <Text style={styles.requestUsername}>@{item.username}</Text>
      </View>
      <View style={styles.requestActions}>
        <TouchableOpacity
          style={[styles.requestButton, styles.acceptButton]}
          onPress={() => respondToFriendRequest(item.friendship_id, 'accept')}
        >
          <Text style={styles.requestButtonText}>Accept</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.requestButton, styles.rejectButton]}
          onPress={() => respondToFriendRequest(item.friendship_id, 'reject')}
        >
          <Text style={styles.requestButtonText}>Reject</Text>
        </TouchableOpacity>
      </View>
    </View>
  );

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>Social</Text>
        <View style={styles.tabContainer}>
          <TouchableOpacity
            style={[styles.tab, activeTab === 'friends' && styles.activeTab]}
            onPress={() => setActiveTab('friends')}
          >
            <Text style={[styles.tabText, activeTab === 'friends' && styles.activeTabText]}>
              Friends
            </Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.tab, activeTab === 'trips' && styles.activeTab]}
            onPress={() => setActiveTab('trips')}
          >
            <Text style={[styles.tabText, activeTab === 'trips' && styles.activeTabText]}>
              Trips
            </Text>
          </TouchableOpacity>
        </View>
      </View>

      {activeTab === 'friends' && (
        <View style={styles.content}>
          <View style={styles.actions}>
            <TouchableOpacity
              style={styles.actionButton}
              onPress={() => setShowSearchModal(true)}
            >
              <Text style={styles.actionButtonText}>Add Friends</Text>
            </TouchableOpacity>
          </View>

          {friendRequests.length > 0 && (
            <View style={styles.section}>
              <Text style={styles.sectionTitle}>Friend Requests ({friendRequests.length})</Text>
              <FlatList
                data={friendRequests}
                renderItem={renderFriendRequest}
                keyExtractor={(item) => item.friendship_id.toString()}
                style={styles.list}
              />
            </View>
          )}

          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Your Friends ({friends.length})</Text>
            <FlatList
              data={friends}
              renderItem={renderFriend}
              keyExtractor={(item) => item.id.toString()}
              style={styles.list}
            />
          </View>
        </View>
      )}

      {activeTab === 'trips' && (
        <View style={styles.content}>
          <View style={styles.actions}>
            <TouchableOpacity
              style={styles.actionButton}
              onPress={() => setShowCreateTripModal(true)}
            >
              <Text style={styles.actionButtonText}>Create Trip</Text>
            </TouchableOpacity>
          </View>

          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Your Trips ({trips.length})</Text>
            <FlatList
              data={trips}
              renderItem={renderTrip}
              keyExtractor={(item) => item.id.toString()}
              style={styles.list}
            />
          </View>
        </View>
      )}

      {/* Search Modal */}
      <Modal visible={showSearchModal} animationType="slide">
        <View style={styles.modalContainer}>
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>Add Friends</Text>
            <TouchableOpacity onPress={() => setShowSearchModal(false)}>
              <Text style={styles.closeButton}>✕</Text>
            </TouchableOpacity>
          </View>
          <TextInput
            style={styles.searchInput}
            placeholder="Search by username or name..."
            value={searchQuery}
            onChangeText={setSearchQuery}
            onSubmitEditing={searchUsers}
          />
          <FlatList
            data={searchResults}
            renderItem={({ item }) => (
              <View style={styles.searchResult}>
                <View style={styles.searchResultInfo}>
                  <Text style={styles.searchResultName}>{item.display_name}</Text>
                  <Text style={styles.searchResultUsername}>@{item.username}</Text>
                </View>
                <TouchableOpacity
                  style={styles.addButton}
                  onPress={() => sendFriendRequest(item.id)}
                  disabled={item.friendship_status === 'pending'}
                >
                  <Text style={styles.addButtonText}>
                    {item.friendship_status === 'pending' ? 'Pending' : 'Add'}
                  </Text>
                </TouchableOpacity>
              </View>
            )}
            keyExtractor={(item) => item.id.toString()}
          />
        </View>
      </Modal>

      {/* Create Trip Modal */}
      <Modal visible={showCreateTripModal} animationType="slide">
        <View style={styles.modalContainer}>
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>Create New Trip</Text>
            <TouchableOpacity onPress={() => setShowCreateTripModal(false)}>
              <Text style={styles.closeButton}>✕</Text>
            </TouchableOpacity>
          </View>
          <ScrollView style={styles.modalContent}>
            <TextInput
              style={styles.modalInput}
              placeholder="Trip Name *"
              value={newTripData.name}
              onChangeText={(text) => setNewTripData({ ...newTripData, name: text })}
            />
            <TextInput
              style={styles.modalInput}
              placeholder="Description"
              value={newTripData.description}
              onChangeText={(text) => setNewTripData({ ...newTripData, description: text })}
              multiline
            />
            <TextInput
              style={styles.modalInput}
              placeholder="Destination"
              value={newTripData.destination}
              onChangeText={(text) => setNewTripData({ ...newTripData, destination: text })}
            />
            <TextInput
              style={styles.modalInput}
              placeholder="Start Date (YYYY-MM-DD)"
              value={newTripData.start_date}
              onChangeText={(text) => setNewTripData({ ...newTripData, start_date: text })}
            />
            <TextInput
              style={styles.modalInput}
              placeholder="End Date (YYYY-MM-DD)"
              value={newTripData.end_date}
              onChangeText={(text) => setNewTripData({ ...newTripData, end_date: text })}
            />
            <TouchableOpacity style={styles.createButton} onPress={createTrip}>
              <Text style={styles.createButtonText}>Create Trip</Text>
            </TouchableOpacity>
          </ScrollView>
        </View>
      </Modal>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f5f5',
  },
  header: {
    backgroundColor: '#fff',
    padding: 20,
    paddingTop: 60,
    borderBottomWidth: 1,
    borderBottomColor: '#eee',
  },
  title: {
    fontSize: 24,
    fontWeight: 'bold',
    marginBottom: 20,
  },
  tabContainer: {
    flexDirection: 'row',
    backgroundColor: '#f0f0f0',
    borderRadius: 8,
    padding: 4,
  },
  tab: {
    flex: 1,
    paddingVertical: 12,
    alignItems: 'center',
    borderRadius: 6,
  },
  activeTab: {
    backgroundColor: '#007AFF',
  },
  tabText: {
    fontSize: 16,
    color: '#666',
  },
  activeTabText: {
    color: '#fff',
    fontWeight: '600',
  },
  content: {
    flex: 1,
    padding: 20,
  },
  actions: {
    marginBottom: 20,
  },
  actionButton: {
    backgroundColor: '#007AFF',
    padding: 15,
    borderRadius: 8,
    alignItems: 'center',
  },
  actionButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  section: {
    marginBottom: 20,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '600',
    marginBottom: 10,
  },
  list: {
    flex: 1,
  },
  friendItem: {
    backgroundColor: '#fff',
    padding: 15,
    borderRadius: 8,
    marginBottom: 10,
  },
  friendInfo: {
    marginBottom: 5,
  },
  friendName: {
    fontSize: 16,
    fontWeight: '600',
  },
  friendUsername: {
    fontSize: 14,
    color: '#666',
  },
  friendDate: {
    fontSize: 12,
    color: '#999',
  },
  tripItem: {
    backgroundColor: '#fff',
    padding: 15,
    borderRadius: 8,
    marginBottom: 10,
  },
  tripHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 5,
  },
  tripName: {
    fontSize: 16,
    fontWeight: '600',
  },
  tripRole: {
    fontSize: 12,
    color: '#007AFF',
    backgroundColor: '#e3f2fd',
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 4,
  },
  tripDescription: {
    fontSize: 14,
    color: '#666',
    marginBottom: 5,
  },
  tripDestination: {
    fontSize: 14,
    color: '#666',
    marginBottom: 5,
  },
  tripFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  tripMembers: {
    fontSize: 12,
    color: '#999',
  },
  tripDate: {
    fontSize: 12,
    color: '#999',
  },
  requestItem: {
    backgroundColor: '#fff',
    padding: 15,
    borderRadius: 8,
    marginBottom: 10,
  },
  requestInfo: {
    marginBottom: 10,
  },
  requestName: {
    fontSize: 16,
    fontWeight: '600',
  },
  requestUsername: {
    fontSize: 14,
    color: '#666',
  },
  requestActions: {
    flexDirection: 'row',
    gap: 10,
  },
  requestButton: {
    flex: 1,
    padding: 10,
    borderRadius: 6,
    alignItems: 'center',
  },
  acceptButton: {
    backgroundColor: '#4CAF50',
  },
  rejectButton: {
    backgroundColor: '#f44336',
  },
  requestButtonText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '600',
  },
  modalContainer: {
    flex: 1,
    backgroundColor: '#fff',
    paddingTop: 60,
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 20,
    borderBottomWidth: 1,
    borderBottomColor: '#eee',
  },
  modalTitle: {
    fontSize: 20,
    fontWeight: 'bold',
  },
  closeButton: {
    fontSize: 24,
    color: '#666',
  },
  searchInput: {
    borderWidth: 1,
    borderColor: '#ddd',
    borderRadius: 8,
    padding: 15,
    margin: 20,
    fontSize: 16,
  },
  searchResult: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 15,
    borderBottomWidth: 1,
    borderBottomColor: '#eee',
  },
  searchResultInfo: {
    flex: 1,
  },
  searchResultName: {
    fontSize: 16,
    fontWeight: '600',
  },
  searchResultUsername: {
    fontSize: 14,
    color: '#666',
  },
  addButton: {
    backgroundColor: '#007AFF',
    paddingHorizontal: 20,
    paddingVertical: 8,
    borderRadius: 6,
  },
  addButtonText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '600',
  },
  modalContent: {
    padding: 20,
  },
  modalInput: {
    borderWidth: 1,
    borderColor: '#ddd',
    borderRadius: 8,
    padding: 15,
    marginBottom: 15,
    fontSize: 16,
  },
  createButton: {
    backgroundColor: '#007AFF',
    padding: 15,
    borderRadius: 8,
    alignItems: 'center',
    marginTop: 10,
  },
  createButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
});

export default SocialScreen;
