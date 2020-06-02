import numpy as np
import FrisPy as fp

Q_COVAR = np.eye(12)*0.2

R_COVAR = np.eye(6)*0.2

class State:
    def __init__(self, x,y,z,dx,dy,dz,phi,theta,gamma,dphi,drho,dgamma):
        self.x=x
        self.y=y
        self.z=z
        self.dx=dx
        self.dy=dy
        self.dz=dz
        self.phi=phi
        self.theta=theta
        self.gamma=gamma
        self.dphi=dphi
        self.drho=drho
        self.dgamma=dgamma
    
    def __str__(self):
        return str(self.aslist())

    def aslist(self):
        return [ self.x, self.y, self.z, self.dx, self.dy, self.dz, self.phi, self.theta, self.gamma, self.dphi, self.drho, self.dgamma ]

    def update_state(self, args):
        self.update_state_s(*args)

    def update_state_s(self, x,y,z,dx,dy,dz,phi,theta,gamma,dphi,drho,dgamma):
        self.x=x
        self.y=y
        self.z=z
        self.dx=dx
        self.dy=dy
        self.dz=dz
        self.phi=phi
        self.theta=theta
        self.gamma=gamma
        self.dphi=dphi
        self.drho=drho
        self.dgamma=dgamma

class StateEstimator:
    '''State estimator class wrapper'''
    def __init__(self, initial_state):
        '''State estimator initializer. 
        Takes the full set of state variables as input. List-like shape (12,)'''
        
        # Initial condition
        self.state_estimate = State(*initial_state)

        # Initial covariance estimate, E[x0*x0^T],
        # We will use the assumption that the state estimate has:
        #       1. Uncorrelated initial conditions
        #       2. High uncertainty
        self.P_covar_estimate = np.eye(12)*9999

        # Keeps track of whether the state is a priori or a posteriori,
        # in case the Kalman filtering steps are taken out of order
        self.SE_is_a_priori = False

        # Disc
        self.disc = fp.create_disc(initial_conditions = initial_state)
        self.disc.initialize_model()

    def get_state(self):
        return self.state_estimate

    def calc_F_jacobian(self, prev_a_posteori_state, a_priori_state):
        ''' Calculates the jacobian of the dynamics propagation function
        Should be called in dynamics_propagation step.
        '''
        time_step = 0.001
        DT = time_step

        x,y,z,dx,dy,dz,phi,theta,gamma,dphi,dtheta,dgamma = prev_a_posteori_state

        # Calculate discrete difference approximation for df/dx_dot and df/dtheta
        # Get machine epsilon, discrete different step size
        # eps = np.finfo(float).eps*100000000
        eps = 2.220446049250313e-08 # Epsilon chosen to be equal to the integrator's step size
        
        
        jacobian = np.empty((12,12))
        for i in range(12):
            
            apo_state_plus_eps = np.copy(prev_a_posteori_state)
            apo_state_plus_eps[i] += eps

            self.disc.update_coordinates(apo_state_plus_eps)
            times, traj = fp.get_trajectory(self.disc, [0, 0.001], full_trajectory=True)

            df_ds = (traj[1] - a_priori_state) / eps

            jacobian[:,i] = df_ds

        np.savetxt("test.csv",jacobian,delimiter=',')

        return np.array(jacobian)


    def dynamics_propagation(self, a_posteori_state):
        ''' Find the a priori state estimate given the previous a posteori state 
        '''
        if self.SE_is_a_priori:
            raise Exception("Steps computed out of order: dynamics_propogation was called when measurement_update was expected.")

        # Using FrisPy, calculates one time step forward.
        self.disc.update_coordinates(a_posteori_state)
        times, traj = fp.get_trajectory(self.disc, [0, 0.001], full_trajectory=True)
        
        F_jacobian = self.calc_F_jacobian(self.state_estimate.aslist(),traj[1])

        # Assign new estimate
        self.SE_is_a_priori = True
        self.state_estimate.update_state(traj[1])

        # Compute and update the next covariance estimate
        old_P_covar = self.P_covar_estimate
        
        self.P_covar_estimate = F_jacobian @ old_P_covar @ F_jacobian.transpose() + Q_COVAR

        return traj[1]
    
    def measurement_update(self,measurement):
        ''' For some a priori state estimate and measurement,
        compute a posteriori state estimate
        '''
        if not self.SE_is_a_priori:
            raise Exception("Steps computed out of order: measurement_update was called when dynamics_propogation was expected.")
        
        # format predicted measurement
        SE = np.array(self.state_estimate.aslist())
        A = np.array([[ 1,0,0,0,0,0,0,0,0,0,0,0 ],
                      [ 0,1,0,0,0,0,0,0,0,0,0,0 ], 
                      [ 0,0,1,0,0,0,0,0,0,0,0,0 ], 
                      [ 0,0,0,0,0,0,1,0,0,0,0,0 ], 
                      [ 0,0,0,0,0,0,0,1,0,0,0,0 ], 
                      [ 0,0,0,0,0,0,0,0,1,0,0,0 ]] )
        predicted_measurement = A @ SE

        # compute residuals
        residuals = np.array(measurement) - predicted_measurement

        # compute residual covariance
        H_jacobian = A
        S_inv = np.linalg.inv(H_jacobian @ self.P_covar_estimate @ H_jacobian.transpose() + R_COVAR)


        # compute Kalman gain
        kalman_gain = self.P_covar_estimate @ H_jacobian.transpose() @ S_inv
        
        # update Kalman estimate and covariance estimate
        new_state_estimate = np.array(self.state_estimate.aslist()) + np.dot(kalman_gain, residuals)
        
        self.state_estimate.update_state(new_state_estimate)
        self.P_covar_estimate = (np.eye(12) - kalman_gain @ H_jacobian) @ self.P_covar_estimate

        self.SE_is_a_priori = False

        return self.state_estimate.aslist()